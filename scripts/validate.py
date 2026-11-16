"""
Validates the built dist/ tree before it is uploaded. Run after substitute.py.

Errors (exit 1, deploy is blocked):
  * a text file still contains a {{PLACEHOLDER}}
  * an .xml or .json file does not parse
  * cfggameplay.json lists a spawn gear preset file that does not exist
  * a spawn gear preset names an item class that is not in the mission's
    db/types.xml (the game spawns nothing for it, silently)

Warnings (printed, deploy continues):
  * cfgenvironment.xml or cfgeconomycore.xml reference files that are not in
    dist/ (the server may already have them; they are just not managed here)
  * a types.xml entry that spawns (nominal > 0) has min greater than nominal
    (vanilla ships one of these, so it cannot be an error)
  * an events.xml event with <limit>custom</limit> has child percentages that
    run past 100, so the children after that point never spawn
    (vanilla Nasdara ships InfectedCity this way, so it cannot be an error)
"""
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(ROOT, "dist")

TEXT_EXTENSIONS = {".xml", ".json", ".cfg", ".txt", ".ini"}
PLACEHOLDER = re.compile(r"\{\{\w+\}\}")


def rel(path):
    return os.path.relpath(path, DIST_DIR).replace(os.sep, "/")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_text_files(errors):
    for dirpath, _, filenames in os.walk(DIST_DIR):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in TEXT_EXTENSIONS:
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            for m in PLACEHOLDER.finditer(content):
                errors.append(f"{rel(path)}: unresolved placeholder {m.group(0)}")
            if ext == ".xml":
                try:
                    ET.parse(path)
                except ET.ParseError as e:
                    errors.append(f"{rel(path)}: XML does not parse ({e})")
            elif ext == ".json":
                try:
                    json.loads(content)
                except ValueError as e:
                    errors.append(f"{rel(path)}: JSON does not parse ({e})")


def item_classes(node, out):
    """Collect every item class a loadout can spawn."""
    if isinstance(node, dict):
        if node.get("itemType"):
            out.add(node["itemType"])
        out.update(node.get("simpleChildrenTypes") or [])
        for value in node.values():
            item_classes(value, out)
    elif isinstance(node, list):
        for value in node:
            item_classes(value, out)


def check_loadouts(mission, errors):
    gameplay = os.path.join(mission, "cfggameplay.json")
    if not os.path.exists(gameplay):
        return
    try:
        presets = load_json(gameplay).get("PlayerData", {}).get("spawnGearPresetFiles", [])
    except ValueError:
        return  # already reported by check_text_files

    types_path = os.path.join(mission, "db", "types.xml")
    known = None
    if os.path.exists(types_path):
        try:
            known = {t.get("name") for t in ET.parse(types_path).getroot().findall("type")}
        except ET.ParseError:
            pass  # already reported

    for preset in presets:
        path = os.path.join(mission, preset)
        if not os.path.exists(path):
            errors.append(f"{rel(gameplay)}: spawn gear preset {preset} not found")
            continue
        try:
            classes = set()
            item_classes(load_json(path), classes)
        except ValueError:
            continue  # already reported
        if known is None:
            continue
        for cls in sorted(classes - known):
            errors.append(f"{rel(path)}: item class {cls} is not in db/types.xml")


def check_types(mission, warnings):
    """Flag spawning types whose min exceeds nominal.

    Types with nominal 0 are skipped: vanilla ships disabled variants as nominal 0 / min 1.
    This is a warning, not an error, because vanilla types.xml contains one such entry.
    """
    path = os.path.join(mission, "db", "types.xml")
    if not os.path.exists(path):
        return
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return  # already reported
    for t in root.findall("type"):
        nominal = int(t.findtext("nominal") or 0)
        minimum = int(t.findtext("min") or 0)
        if nominal > 0 and minimum > nominal:
            warnings.append(f"{rel(path)}: type {t.get('name')} has min {minimum} > nominal {nominal}")


def check_event_children(mission, warnings):
    """Flag children of a custom-limit event that can never spawn.

    In a <limit>custom</limit> event (every infected event) a child's min is the
    percent of the event's spawn budget it receives. The CE hands the budget out
    in file order, so once earlier children have claimed 100 percent, every child
    after that point is allotted zero pieces and never appears. The server RPT
    shows the result in its "Scaling Spawner" block as "min: 0, max: 0".
    """
    path = os.path.join(mission, "db", "events.xml")
    if not os.path.exists(path):
        return
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return  # already reported
    for event in root.findall("event"):
        if event.findtext("limit") != "custom":
            continue
        claimed = 0
        starved = []
        for child in event.findall("children/child"):
            if claimed >= 100:
                starved.append(child.get("type"))
            claimed += int(child.get("min") or 0)
        if starved:
            warnings.append(
                f"{rel(path)}: event {event.get('name')} child percentages total {claimed}; "
                f"these come after the 100 mark and never spawn: {', '.join(starved)}"
            )


def check_referenced_files(mission, warnings):
    env = os.path.join(mission, "cfgenvironment.xml")
    if os.path.exists(env):
        try:
            for el in ET.parse(env).getroot().iter("file"):
                path = el.get("path")
                if path and not os.path.exists(os.path.join(mission, path)):
                    warnings.append(f"{rel(env)}: references {path}, which is not in dist/")
        except ET.ParseError:
            pass

    core = os.path.join(mission, "cfgeconomycore.xml")
    if os.path.exists(core):
        try:
            for ce in ET.parse(core).getroot().findall("ce"):
                folder = ce.get("folder", "")
                for el in ce.findall("file"):
                    path = os.path.join(folder, el.get("name", ""))
                    if not os.path.exists(os.path.join(mission, path)):
                        warnings.append(f"{rel(core)}: references {path.replace(os.sep, '/')}, which is not in dist/")
        except ET.ParseError:
            pass


def main():
    if not os.path.isdir(DIST_DIR):
        print("ERROR: dist/ does not exist. Run scripts/substitute.py first.")
        return 1

    errors, warnings = [], []
    check_text_files(errors)
    for mission in sorted(glob.glob(os.path.join(DIST_DIR, "dayzxb_missions", "*"))):
        check_loadouts(mission, errors)
        check_types(mission, warnings)
        check_event_children(mission, warnings)
        check_referenced_files(mission, warnings)

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        print(f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1
    print(f"Validation passed ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
