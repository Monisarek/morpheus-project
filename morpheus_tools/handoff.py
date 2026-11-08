"""Durable receipt guard for the existing GitHub, Drive and Slack connectors."""

import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

from .cli import SafeArgumentParser
from .paths import local_path
from .tools.research_registry import json_digest


STATE = Path(".morpheus/handoffs")
STAGES = ("drive", "slack")
GITHUB = "https://github.com/Monisarek/morpheus-project"
CHANNEL = "C0CGMC7NRL0"
WORKSPACE = "morpheusresea-9xx8372.slack.com"


def plan_id(plan):
    if (set(plan) != {"pr", "ci", "head", "thread"}
            or not re.fullmatch(re.escape(GITHUB) + r"/pull/[1-9][0-9]*", plan["pr"])
            or not re.fullmatch(re.escape(GITHUB) + r"/actions/runs/[1-9][0-9]*", plan["ci"])
            or not re.fullmatch(r"[0-9a-f]{40}", plan["head"])
            or not re.fullmatch(r"[0-9]+\.[0-9]{6}", plan["thread"])):
        raise ValueError("invalid_handoff_plan")
    return json_digest({key: plan[key] for key in ("pr", "head", "thread")})


def claim(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())


def read(path):
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("invalid_handoff_file")
    path = local_path(path)
    if not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("invalid_handoff_file")
    return json.loads(path.read_bytes())


def receipt_matches(stage, link, thread):
    url = urlsplit(link)
    if url.scheme != "https" or url.fragment:
        return False
    if stage == "drive":
        return url.netloc == "drive.google.com" and re.fullmatch(r"/file/d/[A-Za-z0-9_-]+/view", url.path)
    query = parse_qs(url.query)
    return (url.netloc == WORKSPACE and re.fullmatch(r"/archives/" + CHANNEL + r"/p[0-9]+", url.path)
            and query.get("thread_ts") == [thread] and query.get("cid") == [CHANNEL])


def transfer(plan, stage, action, link=None, root=STATE):
    if stage not in STAGES:
        raise ValueError("invalid_handoff_stage")
    key = plan_id(plan)
    local_path(root.parent)
    root.mkdir(exist_ok=True)
    root = local_path(root)
    directory = root / key
    directory.mkdir(exist_ok=True)
    directory = local_path(directory)
    intent = directory / (stage + ".intent.json")
    receipt = directory / (stage + ".receipt.json")
    if stage == "slack":
        previous = read(directory / "drive.receipt.json")
        if not receipt_matches("drive", previous["link"], plan["thread"]):
            raise ValueError("unverified_drive_receipt")
    if action == "reserve":
        try:
            claim(intent, {"id": key, "stage": stage})
            return {"status": "SEND_ONCE", "handoff_id": key, "stage": stage}
        except FileExistsError:
            if not receipt.exists():
                return {"status": "RECONCILE", "handoff_id": key, "stage": stage}
            existing = read(receipt)["link"]
            if not receipt_matches(stage, existing, plan["thread"]):
                raise ValueError("unverified_handoff_receipt")
            return {"status": "ALREADY_RECORDED", "handoff_id": key, "stage": stage, "link": existing}
    if (action != "record" or not link or not receipt_matches(stage, link, plan["thread"])
            or read(intent) != {"id": key, "stage": stage}):
        raise ValueError("unverified_handoff_receipt")
    try:
        claim(receipt, {"link": link})
    except FileExistsError:
        if read(receipt) != {"link": link}:
            raise ValueError("conflicting_handoff_receipt") from None
    return {"status": "RECORDED", "handoff_id": key, "stage": stage, "link": link}


def main():
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("action", choices=("reserve", "record"))
    parser.add_argument("--link")
    try:
        args = parser.parse_args()
        result = transfer(read(args.plan), args.stage, args.action, args.link)
    except (OSError, ValueError, KeyError, TypeError):
        print('{"status":"BLOCKED","reason":"invalid_or_unverified_handoff"}')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 3 if result["status"] == "RECONCILE" else 0


if __name__ == "__main__":
    sys.exit(main())
