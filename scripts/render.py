"""Fill ${VAR} placeholders in a template from the environment; fail if any value is missing.

Usage: python3 scripts/render.py TEMPLATE > OUTPUT
"""
import os
import re
import sys

text = open(sys.argv[1]).read()
missing = sorted({v for v in re.findall(r"\$\{(\w+)\}", text) if not os.environ.get(v)})
if missing:
    sys.exit(f"{sys.argv[1]}: set these in config.env first: {', '.join(missing)}")
sys.stdout.write(re.sub(r"\$\{(\w+)\}", lambda m: os.environ[m.group(1)], text))
