"""
Build step: reads config.yml, copies remote/ to dist/, and fills {{VAR}}
placeholders. Then applies the density multipliers to every mission in dist/:

  * env/zombie_territories.xml  dmin/dmax           x INFECTED_GLOBAL_D_MULTIPLIER x <Zone>_D_MULTIPLIER
  * db/events.xml nominal/min/max, Infected* events x INFECTED_GLOBAL_D_MULTIPLIER x <Event>_D_MULTIPLIER
  * db/events.xml nominal/min/max, Animal* events   x ANIMAL_GLOBAL_D_MULTIPLIER   x <Event>_D_MULTIPLIER
  * db/events.xml nominal/min/max, Vehicle* events  x VEHICLE_GLOBAL_D_MULTIPLIER  x <Event>_D_MULTIPLIER
  * db/events.xml Infected* children lootmin/lootmax capped at INFECTED_LOOT_MAX
  * db/types.xml nominal/min per category            x LOOT_<CATEGORY>_MULTIPLIER (e.g. LOOT_FOOD_MULTIPLIER)
  * db/types.xml restock raised to at least LOOT_RESTOCK_MIN seconds

Counts round up, so a scaled-down item never reaches zero unless it already was.

Placeholder rules:
  * XML and other text files: {{VAR}} is replaced verbatim.
  * JSON files: write the placeholder as a string, "{{VAR}}", so the source
    file stays valid JSON for editors. If the value is a number or boolean it
    is emitted bare (2.0, 400, true) so the output is correctly typed;
    anything else is emitted as a JSON string.

Exits non-zero if any placeholder has no value in config.yml, so a broken
build never reaches the server. Warns about config.yml variables nothing uses.
"""
import glob
import json
import math
import os
import re
import shutil
import stat
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yml")
SRC_DIR = os.path.join(ROOT, "remote")
DST_DIR = os.path.join(ROOT, "dist")

TEXT_EXTENSIONS = {".xml", ".json", ".cfg", ".txt", ".ini"}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
QUOTED_PLACEHOLDER = re.compile(r'"\{\{(\w+)\}\}"')
IDENTIFIER = re.compile(r"^\w+$")


def json_literal(value):
    """JSON token for a config value: bare for numbers/booleans, quoted otherwise."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    try:
        parsed = json.loads(text)
    except ValueError:
        return json.dumps(text)
    if isinstance(parsed, (bool, int, float)):
        return text
    return json.dumps(text)


def substitute_file(path, variables, used, missing):
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    def resolve(key):
        if key not in variables:
            missing.add((key, os.path.relpath(path, DST_DIR).replace(os.sep, "/")))
            return None
        used.add(key)
        return variables[key]

    if ext == ".json":
        def quoted(m):
            value = resolve(m.group(1))
            return m.group(0) if value is None else json_literal(value)
        content = QUOTED_PLACEHOLDER.sub(quoted, content)

    def plain(m):
        value = resolve(m.group(1))
        return m.group(0) if value is None else str(value)
    content = PLACEHOLDER.sub(plain, content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def multiplier_for(name, config, used):
    """Combined multiplier for a zone/event name: group global x per-name."""
    if name.startswith("Infected"):
        global_key = "INFECTED_GLOBAL_D_MULTIPLIER"
    elif name.startswith("Animal"):
        global_key = "ANIMAL_GLOBAL_D_MULTIPLIER"
    elif name.startswith("Vehicle"):
        global_key = "VEHICLE_GLOBAL_D_MULTIPLIER"
    else:
        return 1.0
    combined = 1.0
    for key in (global_key, f"{name}_D_MULTIPLIER"):
        if key in config:
            used.add(key)
            combined *= float(config[key])
    return combined


def scale(value, multiplier):
    """Scale a count, rounding up. Zero stays zero."""
    return 0 if value == 0 else math.ceil(value * multiplier)


def apply_territory_multipliers(path, config, used):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_zone(m):
        tag = m.group(0)
        name_m = re.search(r'name="(\w+)"', tag)
        if not name_m:
            return tag
        multiplier = multiplier_for(name_m.group(1), config, used)
        if multiplier == 1.0:
            return tag
        return re.sub(
            r'\b(dmin|dmax)="(\d+)"',
            lambda a: f'{a.group(1)}="{scale(int(a.group(2)), multiplier)}"',
            tag,
        )

    content = re.sub(r"<zone\b[^>]*/>", replace_zone, content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def apply_event_tuning(path, config, used):
    """Scale event counts by the multipliers and cap how much loot infected carry."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    loot_cap = config.get("INFECTED_LOOT_MAX")
    if loot_cap is not None:
        used.add("INFECTED_LOOT_MAX")
        loot_cap = int(loot_cap)

    def replace_event(m):
        name, block = m.group(1), m.group(2)
        multiplier = multiplier_for(name, config, used)
        if multiplier != 1.0:
            block = re.sub(
                r"<(nominal|min|max)>(\d+)</\1>",
                lambda t: f"<{t.group(1)}>{scale(int(t.group(2)), multiplier)}</{t.group(1)}>",
                block,
            )
        if loot_cap is not None and name.startswith("Infected"):
            block = re.sub(
                r'\b(lootmin|lootmax)="(\d+)"',
                lambda a: f'{a.group(1)}="{min(int(a.group(2)), loot_cap)}"',
                block,
            )
        return f'<event name="{name}">{block}</event>'

    content = re.sub(r'<event name="(\w+)">(.*?)</event>', replace_event, content, flags=re.DOTALL)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def apply_types_tuning(path, config, used):
    """Scale loot nominal/min per category and enforce a restock floor in types.xml."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    restock_min = config.get("LOOT_RESTOCK_MIN")
    if restock_min is not None:
        used.add("LOOT_RESTOCK_MIN")
        restock_min = int(restock_min)

    def replace_type(m):
        name, block = m.group(1), m.group(2)
        category = re.search(r'<category name="(\w+)"\s*/>', block)
        if category:
            key = f"LOOT_{category.group(1).upper()}_MULTIPLIER"
            if key in config:
                used.add(key)
                multiplier = float(config[key])
                if multiplier != 1.0:
                    block = re.sub(
                        r"<(nominal|min)>(\d+)</\1>",
                        lambda t: f"<{t.group(1)}>{scale(int(t.group(2)), multiplier)}</{t.group(1)}>",
                        block,
                    )
        if restock_min is not None:
            block = re.sub(
                r"<restock>(\d+)</restock>",
                lambda t: f"<restock>{max(int(t.group(1)), restock_min)}</restock>",
                block,
            )
        return f'<type name="{name}">{block}</type>'

    content = re.sub(r'<type name="([^"]+)">(.*?)</type>', replace_type, content, flags=re.DOTALL)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _force_remove(func, path, _exc):
    """rmtree hook: clear a read-only attribute and retry the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def reset_dist():
    """Rebuild dist/ as a writable copy of remote/, whatever attributes the source files carry."""
    if os.path.exists(DST_DIR):
        shutil.rmtree(DST_DIR, onexc=_force_remove)
    # copyfile copies content only, so read-only bits on remote/ do not follow into dist/.
    shutil.copytree(SRC_DIR, DST_DIR, copy_function=shutil.copyfile)


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    reset_dist()

    used, missing = set(), set()
    for dirpath, _, filenames in os.walk(DST_DIR):
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in TEXT_EXTENSIONS:
                substitute_file(os.path.join(dirpath, filename), config, used, missing)

    for mission in sorted(glob.glob(os.path.join(DST_DIR, "dayzxb_missions", "*"))):
        apply_territory_multipliers(os.path.join(mission, "env", "zombie_territories.xml"), config, used)
        apply_event_tuning(os.path.join(mission, "db", "events.xml"), config, used)
        apply_types_tuning(os.path.join(mission, "db", "types.xml"), config, used)

    for key in sorted({k for k in config if IDENTIFIER.match(k)} - used):
        print(f"WARNING: config.yml variable {key} is not used by anything in remote/")

    if missing:
        for key, rel in sorted(missing):
            print(f"ERROR: {{{{{key}}}}} in {rel} has no value in config.yml")
        print(f"Build failed: {len(missing)} unresolved placeholder(s).")
        return 1

    print(f"Built dist/ ({len(used)} variable(s) applied).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
