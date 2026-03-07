"""
Reads config.yml, copies remote/ to dist/, and replaces {{VAR}} placeholders.
"""
import os
import re
import shutil
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yml")
SRC_DIR = os.path.join(ROOT, "remote")
DST_DIR = os.path.join(ROOT, "dist")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Strip comments from config (yaml.safe_load already handles this)
variables = {k: str(v) for k, v in config.items()}

if os.path.exists(DST_DIR):
    shutil.rmtree(DST_DIR)
shutil.copytree(SRC_DIR, DST_DIR)

pattern = re.compile(r"\{\{(\w+)\}\}")
text_extensions = {".xml", ".json", ".cfg", ".txt", ".ini"}

for dirpath, _, filenames in os.walk(DST_DIR):
    for filename in filenames:
        if os.path.splitext(filename)[1].lower() not in text_extensions:
            continue
        filepath = os.path.join(dirpath, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        def replacer(match):
            key = match.group(1)
            if key not in variables:
                print(f"  WARNING: {{{{ {key} }}}} not found in config.yml ({filepath})")
                return match.group(0)
            return variables[key]

        new_content = pattern.sub(replacer, content)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

print(f"Built dist/ with {len(variables)} variable(s) substituted.")
