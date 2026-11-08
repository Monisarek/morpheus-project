"""One explicitly approved public pilot for the existing Slack Dispatcher."""

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess

TASK = "MR-019"
RECORD = "Rec0CFMN7KJ9K"
PILOT = "iris-sepal-v1"
THREAD = "1794065078.911019"
FILES = ("lab.py", "iris_pilot.py", "dispatch_worker.py", "fixtures/iris.csv",
         "protocols/iris-sepal-v1.json", "evidence/iris-sepal-v1.json")
COMMAND = re.compile(r"<@U0CFBPD8KV5(?:\|[^>\r\n]+)?> (run|resume) MR-019 iris-sepal-v1")
FOOTER = re.compile(r"\*Sent using\* <@[A-Z0-9]+(?:\|[^>\r\n]+)?>")
TS = re.compile(r"[0-9]{10}\.[0-9]{6}")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
CONTAINER = "morpheus-mr019-iris-sepal-v1"
LOCAL_ENGINE = "npipe:////./pipe/dockerDesktopLinuxEngine"


class Denied(ValueError):
    pass


def authorize(event, owner, channel):
    raw = event.get("text")
    if (event.get("user") != owner or event.get("channel") != channel
            or event.get("bot_id") or event.get("subtype") or event.get("thread_ts") != THREAD
            or not TS.fullmatch(str(event.get("ts", "")))
            or not isinstance(raw, str) or len(raw) > 512):
        return None
    lines = raw.strip().splitlines()
    if not lines or len(lines) > 2 or (len(lines) == 2 and not FOOTER.fullmatch(lines[1])):
        return None
    matched = COMMAND.fullmatch(lines[0])
    return matched[1] if matched else None


def safe_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise Denied("unsafe_pilot_directory")


def safe_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise Denied("unsafe_pilot_file")
    return path.read_bytes()


def approval(root, source):
    safe_directory(root)
    safe_directory(source)
    packet = json.loads(safe_file(root / "approval.json"))
    if (not isinstance(packet, dict) or set(packet) != {"pilot", "image", "files"}
            or packet["pilot"] != PILOT or not IMAGE.fullmatch(str(packet["image"]))
            or not isinstance(packet["files"], dict) or set(packet["files"]) != set(FILES)):
        raise Denied("invalid_local_approval")
    directories = {Path(name).parent.as_posix() for name in FILES} - {"."}
    if {entry.name for entry in source.iterdir()} != directories | {n for n in FILES if "/" not in n}:
        raise Denied("unexpected_pilot_input")
    for directory in directories:
        safe_directory(source / directory)
        if {(Path(directory) / entry.name).as_posix() for entry in (source / directory).iterdir()} != {
            name for name in FILES if name.startswith(directory + "/")
        }:
            raise Denied("unexpected_pilot_input")
    for name in FILES:
        target = source / name
        safe_directory(target.parent)
        if sha256(safe_file(target)).hexdigest() != packet["files"][name]:
            raise Denied("approved_input_changed")
    return packet


def docker(root, source, image, resume):
    """Only the public allowlist mount and the job's isolated checkpoint are visible."""
    docker_cli = shutil.which("docker.exe" if os.name == "nt" else "docker")
    if not docker_cli:
        raise Denied("local_docker_unavailable")
    state = root / "state"
    state.mkdir(exist_ok=True)
    safe_directory(state)
    if any("," in str(p) for p in (source, state)):
        raise Denied("unsafe_docker_mount")
    env = {key: os.environ[key] for key in
           ("SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA")
           if key in os.environ}
    engine = LOCAL_ENGINE if os.name == "nt" else "unix:///var/run/docker.sock"
    args = [docker_cli, "--host", engine]

    def call(*command, timeout=6):
        return subprocess.run([*args, *command], env=env, cwd=root, capture_output=True,
                              text=True, encoding="utf-8", timeout=timeout, check=False)

    if resume:
        known = call("container", "ls", "--all", "--filter", f"name=^/{CONTAINER}$",
                     "--format", "{{.Names}}")
        if known.returncode or known.stdout.strip():
            return {"status": "RECONCILE"}
    try:
        result = call(
            "run", "--rm", "--name", CONTAINER, "--pull=never", "--network=none",
            "--read-only", "--user", "65534:65534", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--memory=128m", "--memory-swap=128m",
            "--cpus=0.5", "--pids-limit=32", "--ipc=private", "--shm-size=4m", "--stop-timeout=2",
            "--ulimit", "fsize=1048576:1048576",
            "--log-driver=none", "--mount", f"type=bind,source={source},target=/pilot,readonly",
            "--mount", f"type=bind,source={state},target=/state",
            "--entrypoint", "python", image, "-E", "-s", "-B", "/pilot/dispatch_worker.py",
            timeout=35,
        )
    except subprocess.TimeoutExpired:
        return {"status": "RECONCILE"}
    if result.returncode != 0:
        return {"status": "RECONCILE"}
    parsed = json.loads(result.stdout)
    return parsed if isinstance(parsed, dict) else {"status": "RECONCILE"}


def dispatch(db_path, root, source, action, timestamp, tasks, executor=docker):
    eligible = [task for task in tasks if task.get("ID") == TASK]
    if (len(eligible) != 1 or eligible[0].get("record_id") != RECORD
            or eligible[0].get("Статус") != "IN_PROGRESS"):
        raise Denied("slack_task_not_eligible")
    packet = approval(root, source)
    fingerprint = sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
    with closing(sqlite3.connect(db_path, timeout=0)) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT slack_record_id,state FROM dispatch_queue WHERE task_id=?", (TASK,)).fetchone()
        if row != (RECORD, "PENDING"):
            raise Denied("task_not_pending")
        # Store one execution receipt in the existing database. The queue stays compatible.
        db.execute("""CREATE TABLE IF NOT EXISTS dispatch_iris_receipt (
            task TEXT PRIMARY KEY, approval TEXT NOT NULL, last_event TEXT NOT NULL,
            state TEXT NOT NULL, evidence TEXT)""")
        prior = db.execute("SELECT approval,last_event,state,evidence FROM dispatch_iris_receipt WHERE task=?",
                           (TASK,)).fetchone()
        if prior and prior[0] != fingerprint:
            raise Denied("execution_approval_changed")
        if prior and timestamp <= prior[1]:
            return {"status": "DUPLICATE_EVENT"}
        if prior and prior[2] == "COMPLETED":
            db.execute("UPDATE dispatch_iris_receipt SET last_event=? WHERE task=?", (timestamp, TASK))
            db.commit()
            return {"status": "ALREADY_COMPLETED", "evidence_sha256": prior[3]}
        if (action == "resume") != bool(prior):
            raise Denied("use_explicit_run_or_resume")
        db.execute("INSERT OR REPLACE INTO dispatch_iris_receipt VALUES (?,?,?,?,NULL)",
                   (TASK, fingerprint, timestamp, "RUNNING"))
        db.commit()

    result = executor(root, source, packet["image"], action == "resume")
    evidence = safe_file(source / "evidence/iris-sepal-v1.json")
    complete = (result.get("status") == "COMPLETED" and type(result.get("reused")) is bool
                and result.get("artifact") == json.loads(evidence))
    evidence_sha = sha256(evidence).hexdigest() if complete else None
    state = "COMPLETED" if complete else "RECONCILE"
    with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
        db.execute("UPDATE dispatch_iris_receipt SET state=?,evidence=? WHERE task=? AND last_event=?",
                   (state, evidence_sha, TASK, timestamp))
    return {"status": state, "evidence_sha256": evidence_sha, "reused": result.get("reused")}


def handle(event, owner, channel, db_path, root, source, fetch_tasks, reply, *, executor=docker):
    action = authorize(event, owner, channel)
    if action is None:
        return False
    try:
        # Serialize dispatch invocations without holding the shared queue transaction.
        # The lock is released by the OS even when the Dispatcher is killed.
        safe_directory(root)
        with closing(sqlite3.connect(root / "dispatch-worker.sqlite3", timeout=0)) as lock:
            lock.execute("BEGIN IMMEDIATE")
            result = dispatch(db_path, root, source, action, event["ts"], fetch_tasks(), executor)
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError):
        result = {"status": "BLOCKED"}
    if result["status"] == "DUPLICATE_EVENT":
        return True
    # Final publication uses the existing receipt guard after independent evidence readback.
    message = f"MR-019 · {PILOT} · {result['status']}"
    if result.get("evidence_sha256"):
        message += f" · SHA-256 {result['evidence_sha256']}"
    if result.get("reused") is not None:
        message += f" · reused={str(result['reused']).lower()}"
    reply(message)
    return True
