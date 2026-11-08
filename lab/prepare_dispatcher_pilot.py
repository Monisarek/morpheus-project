"""Prepare only the approved public Iris input tree and an explicit local approval."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

from dispatcher_pilot import FILES, IMAGE, PILOT, approval, safe_directory

LAB = Path(__file__).resolve().parent


def prepare(root, image):
    if not IMAGE.fullmatch(image):
        raise ValueError("a local immutable image ID is required")
    safe_directory(root.parent)
    root.mkdir()
    source = root / "public"
    source.mkdir()
    files = {}
    for name in FILES:
        target = source / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(LAB / name, target)
        files[name] = sha256(target.read_bytes()).hexdigest()
    shutil.copyfile(LAB / "dispatcher_pilot.py", root / "dispatcher_pilot.py")
    packet = {"pilot": PILOT, "image": image, "files": files}
    with (root / "approval.json").open("x", encoding="utf-8") as stream:
        json.dump(packet, stream, indent=2, sort_keys=True)
    approval(root, source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("root", type=Path)
    parser.add_argument("image")
    args = parser.parse_args()
    prepare(args.root.absolute(), args.image)
