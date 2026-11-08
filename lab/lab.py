"""Offline runner for a single built-in synthetic task."""

import argparse
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import version
import json
from math import comb, isfinite
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import time

@dataclass(frozen=True)
class Protocol:
    task: str = "synthetic-control"
    dataset: str = "SYNTHETIC"
    null: str = "P(positive paired difference) = 0.5"
    alpha: float = 0.05
    differences: tuple[int, ...] = (1, -1, 2, -2, 3, -3, 4, -4)


PROTOCOL = Protocol()
STATE = Path(__file__).resolve().parent / ".state"
RESUME = "py lab/lab.py resume --task synthetic-control"
STATES = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "WAITING_QUOTA"}


class CheckpointError(ValueError):
    pass


class QuotaRejected(Exception):
    """The provider definitively rejected the call before doing work."""

    def __init__(self, retry_after_seconds):
        if type(retry_after_seconds) is not int or not 0 <= retry_after_seconds <= 2**53:
            raise ValueError("invalid_retry_after")
        self.seconds = retry_after_seconds


@dataclass(frozen=True)
class Stage:
    name: str
    action: Callable
    external: bool = False


def verify(differences, pvalue):
    count = len(differences)
    positives = sum(value > 0 for value in differences)
    tail = min(positives, count - positives)
    expected = min(1.0, 2 * sum(comb(count, k) for k in range(tail + 1)) / 2**count)
    if abs(pvalue - expected) > 1e-12 or not 0 <= pvalue <= 1:
        raise ValueError("Independent sign test disagrees")


def prepare(packet):
    differences = packet["differences"]
    if not differences or any(type(value) is not int or value == 0 for value in differences):
        raise ValueError("Synthetic protocol requires nonzero integer differences")
    return {"differences": differences, "alpha": packet["alpha"], "dataset": packet["dataset"]}


def compute(prepared=None):
    from scipy.stats import binomtest

    prepared = prepare(asdict(PROTOCOL)) if prepared is None else prepared
    differences = prepared["differences"]
    positives = sum(value > 0 for value in differences)
    pvalue = binomtest(positives, len(differences)).pvalue
    verify(differences, pvalue)
    return {
        "dataset": prepared["dataset"],
        "pairs": len(differences),
        "positive": positives,
        "pvalue": pvalue,
        "decision": "REJECT_NULL" if pvalue < prepared["alpha"] else "NO_EVIDENCE_OF_EFFECT",
        "check": "EXACT_BINOMIAL_REPLAY",
        "scope": "SYNTHETIC_ONLY",
    }


def guard(directory):
    # shortcut: guard fixed paths against static aliases, use OS isolation for untrusted writers
    paths = (directory, *(directory / (name + suffix)
                          for name in ("evidence.sqlite3", "worker.sqlite3")
                          for suffix in ("", "-journal", "-wal", "-shm")))
    for path in paths:
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        expected = stat.S_ISDIR if path == directory else stat.S_ISREG
        if reparse or not expected(info.st_mode) or (path != directory and info.st_nlink != 1):
            raise CheckpointError("unsafe_checkpoint_path")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def row_checksum(stage, state, result_digest, reason, retry_at, retry_used):
    return digest(encode([stage, state, result_digest, reason, retry_at, retry_used]))


def initialize(db, frozen, plan):
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE run (packet TEXT NOT NULL, digest TEXT NOT NULL)")
        db.execute("""CREATE TABLE checkpoints (
            position INTEGER PRIMARY KEY, stage TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
            result TEXT, digest TEXT, reason TEXT, retry_at REAL, retry_used INTEGER NOT NULL DEFAULT 0,
            checksum TEXT NOT NULL
        )""")
        db.execute("INSERT INTO run VALUES (?, ?)", (frozen, digest(frozen)))
        db.executemany("INSERT INTO checkpoints (position, stage, status, checksum) VALUES (?, ?, 'PENDING', ?)",
                       ((i, name, row_checksum(name, "PENDING", None, None, None, 0))
                        for i, (name, _) in enumerate(plan)))


def load(db):
    if [row[0] for row in db.execute("PRAGMA quick_check")] != ["ok"]:
        raise CheckpointError("corrupt_checkpoint")
    metadata = db.execute("SELECT packet, digest FROM run").fetchall()
    if len(metadata) != 1 or digest(metadata[0][0]) != metadata[0][1]:
        raise CheckpointError("corrupt_checkpoint")
    frozen = metadata[0][0]
    manifest = json.loads(frozen)
    if manifest["schema_version"] != 1:
        raise CheckpointError("unsupported_checkpoint_version")
    plan = manifest["plan"]
    rows = db.execute("SELECT * FROM checkpoints ORDER BY position").fetchall()
    if not plan or len(rows) != len(plan):
        raise CheckpointError("corrupt_checkpoint")
    complete_prefix = True
    for index, row in enumerate(rows):
        state = row["status"]
        if (row["position"] != index or row["stage"] != plan[index][0] or state not in STATES
                or row["retry_used"] not in (0, 1) or (not complete_prefix and state != "PENDING")):
            raise CheckpointError("corrupt_checkpoint")
        if row["checksum"] != row_checksum(row["stage"], state, row["digest"], row["reason"],
                                           row["retry_at"], row["retry_used"]):
            raise CheckpointError("corrupt_checkpoint")
        if state == "COMPLETED":
            if not isinstance(row["result"], str) or digest(row["result"]) != row["digest"]:
                raise CheckpointError("corrupt_checkpoint")
            if encode(json.loads(row["result"])) != row["result"]:
                raise CheckpointError("corrupt_checkpoint")
        elif row["result"] is not None or row["digest"] is not None:
            raise CheckpointError("corrupt_checkpoint")
        if state == "WAITING_QUOTA":
            if not isinstance(row["retry_at"], (int, float)) or not isfinite(row["retry_at"]) or row["retry_at"] < 0:
                raise CheckpointError("corrupt_checkpoint")
        elif row["retry_at"] is not None:
            raise CheckpointError("corrupt_checkpoint")
        complete_prefix &= state == "COMPLETED"
    return frozen, rows


def save(db, stage, state, *, body=None, reason=None, retry_at=None, retry_used=0):
    result_digest = digest(body) if body is not None else None
    checksum = row_checksum(stage, state, result_digest, reason, retry_at, retry_used)
    with db:
        db.execute("""UPDATE checkpoints SET status=?, result=?, digest=?, reason=?, retry_at=?, retry_used=?, checksum=?
                      WHERE stage=?""",
                   (state, body, result_digest, reason, retry_at, retry_used, checksum, stage))


def waiting(stage, retry_at, retry_used):
    return {"status": "WAITING_QUOTA", "stage": stage, "retry_at": retry_at,
            "next_command": None if retry_used else RESUME + " --retry-quota"}


def failed(stage, reason, external):
    return {"status": "FAILED", "stage": stage, "reason": reason,
            "next_command": None if external else RESUME}


def advance(db, rows, stages, retry_quota, clock):
    previous = None
    reused = True
    for row, stage in zip(rows, stages):
        state, used = row["status"], row["retry_used"]
        if state == "COMPLETED":
            previous = json.loads(row["result"])
            continue
        if stage.external and state in ("RUNNING", "FAILED"):
            reason = "external_result_unknown"
            save(db, stage.name, "FAILED", reason=reason, retry_used=used)
            return failed(stage.name, reason, True)
        if state == "WAITING_QUOTA":
            if not retry_quota or used or clock() < row["retry_at"]:
                return waiting(stage.name, row["retry_at"], used)
            used = 1
        save(db, stage.name, "RUNNING", retry_used=used)
        try:
            body = encode(stage.action(previous))
        except QuotaRejected as exc:
            if stage.external:
                retry_at = float(clock() + exc.seconds)
                save(db, stage.name, "WAITING_QUOTA", retry_at=retry_at, retry_used=used)
                return waiting(stage.name, retry_at, used)
            save(db, stage.name, "FAILED", reason="local_stage_failed", retry_used=used)
            return failed(stage.name, "local_stage_failed", False)
        except Exception:
            reason = "external_result_unknown" if stage.external else "local_stage_failed"
            save(db, stage.name, "FAILED", reason=reason, retry_used=used)
            return failed(stage.name, reason, stage.external)
        save(db, stage.name, "COMPLETED", body=body, retry_used=used)
        previous = json.loads(body)
        reused = False
    return {"status": "COMPLETED", "artifact": previous, "reused": reused, "next_command": None}


def run(directory, *, packet=None, stages=None, retry_quota=False, clock=time.time):
    if packet is None:
        packet = asdict(PROTOCOL) | {"runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                                    "python": sys.version.split()[0], "scipy": version("scipy")}
    packet = json.loads(encode(packet))
    if stages is None:
        stages = (Stage("prepare", lambda _: prepare(packet)), Stage("compute", compute))
    stages = tuple(stages)
    plan = [(stage.name, stage.external) for stage in stages]
    if (not plan or len({name for name, _ in plan}) != len(plan)
            or any(not isinstance(name, str) or not name or type(external) is not bool for name, external in plan)):
        raise CheckpointError("invalid_stage_plan")
    frozen = encode({"schema_version": 1, "inputs": packet, "plan": plan})
    directory.mkdir(exist_ok=True)
    guard(directory)
    database, worker = directory / "evidence.sqlite3", directory / "worker.sqlite3"
    known = worker.exists()
    try:
        # Keep the OS-owned SQLite writer lock across checkpoint commits and stage execution.
        with closing(sqlite3.connect(worker, timeout=30)) as lock:
            lock.execute("BEGIN IMMEDIATE")
            exists = database.exists()
            if not exists and known:
                raise CheckpointError("missing_checkpoint")
            with closing(sqlite3.connect(database, timeout=30)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA synchronous=EXTRA")
                if not exists:
                    initialize(db, frozen, plan)
                stored, rows = load(db)
                if stored != frozen:
                    raise CheckpointError("inputs_or_stage_plan_changed")
                return advance(db, rows, stages, retry_quota, clock)
    except sqlite3.OperationalError as exc:
        if str(exc) in ("database is locked", "database table is locked"):
            return {"status": "RUNNING", "reason": "checkpoint_busy", "next_command": RESUME}
        raise CheckpointError("checkpoint_unavailable_or_legacy") from None
    except (sqlite3.DatabaseError, TypeError, KeyError, IndexError, AttributeError, ValueError) as exc:
        if isinstance(exc, CheckpointError):
            raise
        raise CheckpointError("corrupt_checkpoint") from None


def status(directory):
    guard(directory)
    database = directory / "evidence.sqlite3"
    if not database.exists():
        if (directory / "worker.sqlite3").exists():
            raise CheckpointError("missing_checkpoint")
        return []
    try:
        with closing(sqlite3.connect(database.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            _, rows = load(db)
            return [{key: row[key] for key in ("stage", "status", "reason", "retry_at", "retry_used")} for row in rows]
    except (sqlite3.DatabaseError, TypeError, KeyError, IndexError, AttributeError, ValueError):
        raise CheckpointError("checkpoint_unavailable_corrupt_or_legacy") from None


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid command or task. Use --help.\n")


def main():
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("doctor", "status", "run", "resume"):
        sub = commands.add_parser(command, allow_abbrev=False)
        if command in ("run", "resume"):
            sub.add_argument("--task", choices=[PROTOCOL.task], required=True)
        if command == "resume":
            sub.add_argument("--retry-quota", action="store_true")
    args = parser.parse_args()
    if args.command == "doctor":
        result = {"python": sys.version.split()[0], "scipy": version("scipy"), "sqlite": sqlite3.sqlite_version,
                  "dvc_on_path": shutil.which("dvc") is not None, "scope": "SYNTHETIC_ONLY", "lab_ready": False}
    else:
        try:
            result = status(STATE) if args.command == "status" else run(
                STATE, retry_quota=getattr(args, "retry_quota", False)
            )
        except CheckpointError as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
            return 2
    print(json.dumps(result, indent=2))
    return 3 if isinstance(result, dict) and result.get("status") in ("RUNNING", "WAITING_QUOTA", "FAILED") else 0


if __name__ == "__main__":
    sys.exit(main())
