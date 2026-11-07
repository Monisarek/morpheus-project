"""Strict, small, human-reviewable inventory of trusted tools."""
import importlib
import json
import re
from pathlib import Path

REGISTRY_FILE = Path(__file__).with_name("registry.json")
EXTERNAL_FILE = Path(__file__).with_name("external_commands.json")
_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*)+$")
_MODULE = re.compile(r"^morpheus_tools\.tools\.[a-z][a-z0-9_]*$")


def load():
    catalog = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("tools"), list):
        raise ValueError("unsupported_registry_schema")
    ids = set()
    for entry in catalog["tools"]:
        name = entry.get("id", "")
        if not _ID.fullmatch(name) or name in ids:
            raise ValueError("invalid_or_duplicate_tool_id")
        ids.add(name)
        if not _MODULE.fullmatch(entry.get("module", "")):
            raise ValueError("module_not_allowlisted")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", entry.get("operation", "")):
            raise ValueError("invalid_operation")
        for field in ("version", "description", "triggers", "example", "risk"):
            if field not in entry:
                raise ValueError("missing_field_" + field)
        if entry["risk"] != "read_only":
            raise ValueError("unreviewed_write_capability")
    return catalog["tools"]


def get(tool_id):
    for entry in load():
        if entry["id"] == tool_id:
            return entry
    raise ValueError("unknown_tool")


def resolve(entry):
    module = importlib.import_module(entry["module"])
    if not hasattr(module, "add_arguments") or not hasattr(module, "execute"):
        raise ValueError("invalid_tool_interface")
    return module


def validate():
    items = load()
    ext = external()
    for entry in items:
        resolve(entry)
    return {"total": len(items) + len(ext), "executable": len(items), "documented_external": len(ext)}


def external():
    """Documented existing EEG commands: inventory-only, not executed here."""
    data = json.loads(EXTERNAL_FILE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("tools"), list):
        raise ValueError("unsupported_external_catalog_schema")
    names = {t["id"] for t in load()}
    for entry in data["tools"]:
        if not _ID.fullmatch(entry.get("id", "")) or entry["id"] in names:
            raise ValueError("duplicate_external_id")
        names.add(entry["id"])
        for key in ("description", "triggers", "example", "risk", "status"):
            if key not in entry:
                raise ValueError("invalid_external_entry")
    return data["tools"]


def inventory():
    return [{**item, "kind": "executable"} for item in load()] + [{**item, "kind": "documented_external"} for item in external()]
