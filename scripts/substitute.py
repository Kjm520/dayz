"""
Build step: reads each map's config, copies remote/ to dist/, fills {{VAR}}
placeholders, then applies the density and loot tuning to every mission in dist/.

Config:
  * config.<map>.yml   the complete config for one mission: config.sakhal.yml
                       applies to dayzxb_missions/dayzOffline.sakhal (the part
                       after the dot). Nothing is shared between maps. A mission
                       folder without a config file fails the build, and a file
                       outside every mission folder cannot carry placeholders.
                       A config for an official map with no mission folder is
                       parked (kept for a later switch) and ignored; any other
                       unmatched config is warned about as a likely typo.

Tuning applied per mission, keys looked up in that mission's config:
  * env/zombie_territories.xml  dmin/dmax           x INFECTED_GLOBAL_D_MULTIPLIER x <Zone>_D_MULTIPLIER
  * db/events.xml nominal/min/max, Infected* events x INFECTED_GLOBAL_D_MULTIPLIER x <Event>_D_MULTIPLIER
  * db/events.xml nominal/min/max, Animal* events   x ANIMAL_GLOBAL_D_MULTIPLIER   x <Event>_D_MULTIPLIER
  * db/events.xml nominal/min/max, Vehicle* events  x VEHICLE_GLOBAL_D_MULTIPLIER  x <Event>_D_MULTIPLIER
  * db/events.xml Infected* children lootmin/lootmax capped at INFECTED_LOOT_MAX
  * db/types.xml nominal/min per category            x LOOT_<CATEGORY>_MULTIPLIER (e.g. LOOT_FOOD_MULTIPLIER)
  * db/types.xml restock raised to at least LOOT_RESTOCK_MIN seconds
  * db/types.xml min (only) x LOOT_MIN_MULTIPLIER, widening the gap below nominal

Counts round up, so a scaled-down item never reaches zero unless it already was.
The exception is LOOT_MIN_MULTIPLIER, which rounds down (floored at 1) so that
small thresholds actually move: a min of 3 at 0.85 becomes 2, not 3.

Placeholder rules:
  * XML and other text files: {{VAR}} is replaced verbatim.
  * JSON files: write the placeholder as a string, "{{VAR}}", so the source
    file stays valid JSON for editors. If the value is a number or boolean it
    is emitted bare (2.0, 400, true) so the output is correctly typed;
    anything else is emitted as a JSON string.

Exits non-zero if any placeholder has no value, so a broken build never
reaches the server. Warns about config variables nothing uses.
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
SRC_DIR = os.path.join(ROOT, "remote")
DST_DIR = os.path.join(ROOT, "dist")
MISSIONS_DIR = "dayzxb_missions"
# The console maps. A config.<map>.yml for one of these with no mission folder is
# parked for a later switch, not a typo.
MAPS = {"chernarusplus", "enoch", "sakhal", "nasdara"}

TEXT_EXTENSIONS = {".xml", ".json", ".cfg", ".txt", ".ini"}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
QUOTED_PLACEHOLDER = re.compile(r'"\{\{(\w+)\}\}"')
IDENTIFIER = re.compile(r"^\w+$")


class MissionConfig:
    """One mission's config.

    Records which keys were actually applied, so the build can warn about
    variables nothing uses.
    """

    def __init__(self, name, values):
        self.name = name      # config file name, for messages
        self.values = values
        self.used = set()

    def __contains__(self, key):
        return key in self.values

    def get(self, key, default=None):
        if key in self.values:
            self.used.add(key)
            return self.values[key]
        return default


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def mission_key(folder):
    """dayzOffline.sakhal -> sakhal"""
    return folder.split(".", 1)[1] if "." in folder else folder


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


def substitute_file(path, config, missing):
    """Fill placeholders from config (None outside a mission folder); unresolved ones go in missing."""
    ext = os.path.splitext(path)[1].lower()
    rel = os.path.relpath(path, DST_DIR).replace(os.sep, "/")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    def resolve(key):
        if config is None or key not in config:
            missing.add((rel, key, config.name if config else None))
            return None
        return config.get(key)

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


def multiplier_for(name, config):
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
            combined *= float(config.get(key))
    return combined


def scale(value, multiplier):
    """Scale a count, rounding up. Zero stays zero."""
    return 0 if value == 0 else math.ceil(value * multiplier)


def scale_min(value, multiplier):
    """Scale a min threshold, rounding down but never below 1. Zero stays zero."""
    return 0 if value == 0 else max(1, math.floor(value * multiplier))


def apply_territory_multipliers(path, config):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_zone(m):
        tag = m.group(0)
        name_m = re.search(r'name="(\w+)"', tag)
        if not name_m:
            return tag
        multiplier = multiplier_for(name_m.group(1), config)
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


def apply_event_tuning(path, config):
    """Scale event counts by the multipliers and cap how much loot infected carry."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    loot_cap = config.get("INFECTED_LOOT_MAX")
    if loot_cap is not None:
        loot_cap = int(loot_cap)

    def replace_event(m):
        name, block = m.group(1), m.group(2)
        multiplier = multiplier_for(name, config)
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


def apply_types_tuning(path, config):
    """Scale loot nominal/min per category, widen the min gap, and enforce a restock floor."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    restock_min = config.get("LOOT_RESTOCK_MIN")
    if restock_min is not None:
        restock_min = int(restock_min)

    min_multiplier = config.get("LOOT_MIN_MULTIPLIER")
    if min_multiplier is not None:
        min_multiplier = float(min_multiplier)

    def replace_type(m):
        name, block = m.group(1), m.group(2)
        category = re.search(r'<category name="(\w+)"\s*/>', block)
        if category:
            key = f"LOOT_{category.group(1).upper()}_MULTIPLIER"
            if key in config:
                multiplier = float(config.get(key))
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
        if min_multiplier is not None and min_multiplier != 1.0:
            nominal = re.search(r"<nominal>(\d+)</nominal>", block)
            if nominal and int(nominal.group(1)) > 0:  # leave disabled (nominal 0) types alone
                block = re.sub(
                    r"<min>(\d+)</min>",
                    lambda t: f"<min>{scale_min(int(t.group(1)), min_multiplier)}</min>",
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


def load_configs():
    """One MissionConfig per non-empty mission folder in dist/. Returns (missions, errors)."""
    missions, errors = {}, []
    for mission_dir in sorted(glob.glob(os.path.join(DST_DIR, MISSIONS_DIR, "*"))):
        if not any(files for _, _, files in os.walk(mission_dir)):
            continue  # empty leftover folder, not a mission
        folder = os.path.basename(mission_dir)
        name = f"config.{mission_key(folder)}.yml"
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            errors.append(f"remote/{MISSIONS_DIR}/{folder} has no {name}")
            continue
        missions[folder] = MissionConfig(name, load_yaml(path))

    known_keys = {mission_key(folder) for folder in missions}
    for path in sorted(glob.glob(os.path.join(ROOT, "config.*.yml"))):
        key = os.path.basename(path)[len("config."):-len(".yml")]
        if key not in known_keys and key not in MAPS:
            print(f"WARNING: {os.path.basename(path)} matches no mission under remote/{MISSIONS_DIR}/ and no known map")
    return missions, errors


def config_for(path, missions):
    """The config of the mission a dist/ file belongs to, or None outside every mission folder."""
    parts = os.path.relpath(path, DST_DIR).split(os.sep)
    if len(parts) > 2 and parts[0] == MISSIONS_DIR:
        return missions.get(parts[1])
    return None


def main():
    reset_dist()
    missions, errors = load_configs()
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"Build failed: {len(errors)} mission(s) without a config file.")
        return 1

    missing = set()
    for dirpath, _, filenames in os.walk(DST_DIR):
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in TEXT_EXTENSIONS:
                path = os.path.join(dirpath, filename)
                substitute_file(path, config_for(path, missions), missing)

    for folder, config in missions.items():
        mission = os.path.join(DST_DIR, MISSIONS_DIR, folder)
        apply_territory_multipliers(os.path.join(mission, "env", "zombie_territories.xml"), config)
        apply_event_tuning(os.path.join(mission, "db", "events.xml"), config)
        apply_types_tuning(os.path.join(mission, "db", "types.xml"), config)

    applied = 0
    for folder, config in missions.items():
        applied += len(config.used)
        for key in sorted(k for k in config.values if IDENTIFIER.match(k)):
            if key not in config.used:
                print(f"WARNING: {config.name} variable {key} is not used by {folder}")

    if missing:
        for rel, key, config_name in sorted(missing):
            where = f"has no value in {config_name}" if config_name else "is outside every mission folder, where no config applies"
            print(f"ERROR: {{{{{key}}}}} in {rel} {where}")
        print(f"Build failed: {len(missing)} unresolved placeholder(s).")
        return 1

    print(f"Built dist/ ({applied} variable(s) applied across {len(missions)} mission(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
