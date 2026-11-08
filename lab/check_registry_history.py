"""Keep existing registry records and referenced research artifacts append-only."""

from pathlib import Path
import subprocess
import sys


LEDGER = "lab/registry.jsonl"


def extends_history(previous, current):
    prefix = previous.splitlines()
    return current.splitlines()[:len(prefix)] == prefix


def verify(base):
    def git(*args):
        return subprocess.check_output(["git", *args]).decode("utf-8")

    files = git("diff", "--name-only", "--no-renames", "--diff-filter=DMRTUXB", base, "HEAD", "--",
                "lab/protocols", "lab/evidence", "lab/fixtures").splitlines()
    if any(path.endswith((".json", ".csv")) for path in files):
        raise ValueError("existing_research_artifact_changed")
    if git("ls-tree", "--name-only", base, LEDGER).strip():
        previous = git("show", f"{base}:{LEDGER}")
        if not extends_history(previous, Path(LEDGER).read_text(encoding="utf-8")):
            raise ValueError("research_registry_history_changed")


if __name__ == "__main__":
    verify(sys.argv[1])
