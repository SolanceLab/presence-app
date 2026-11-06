# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""Refresh the Codex plugin from the rooms this set is pinned to (run `make get` first).

Copies each room's skill into plugin/codex-skills/ and points the Antechamber connection at the exact
commit in the Makefile (ANTECHAMBER_SHA), so what a stranger's machine runs is the reviewed commit."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
make = dict(re.findall(r"^([A-Z_]+)\s*=\s*(\S+)", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M))
for room in ("antechamber", "scriptorium", "vault-map"):
    head = subprocess.run(["git", "-C", str(ROOT / "rooms" / room), "rev-parse", "HEAD"], capture_output=True, text=True)
    pinned = make[room.upper().replace("-", "_") + "_SHA"]
    if head.returncode != 0 or head.stdout.strip() != pinned:
        sys.exit(f"rooms/{room} is not at its pinned commit {pinned[:7]}: delete it and run make get again")
    src = ROOT / "rooms" / room / "plugin" / "skills" / room / "SKILL.md"
    if not src.is_file():
        sys.exit(f"rooms/{room} is missing: run make get first")
    dest = ROOT / "plugin" / "codex-skills" / room / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)

conn = ROOT / "plugin" / "codex.mcp.json"
data = json.loads(conn.read_text(encoding="utf-8"))
sha = make["ANTECHAMBER_SHA"]
args = data["mcpServers"]["antechamber"]["args"]
data["mcpServers"]["antechamber"]["args"] = [
    re.sub(r"(github\.com/SolanceLab/antechamber)@\S+", r"\1@" + sha, a) for a in args
]
conn.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print("plugin-codex refreshed from rooms/ (Antechamber pinned to " + sha[:7] + ")")
