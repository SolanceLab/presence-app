# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""Refresh the Codex plugin from the rooms this set is pinned to (run `make get` first).

Copies each room's skill into plugin/codex-skills/ and points the Antechamber connection at the exact
commit in the Makefile (ANTECHAMBER_SHA), so what a stranger's machine runs is the reviewed commit."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def codex_text(room, text):
    """The skill text as Codex gets it: work-map's script paths are rewritten, the other rooms pass through."""
    if room == "work-map":
        # Codex has no CLAUDE_PLUGIN_ROOT: the writers sit two folders above this skill (plugin/scripts), so point there.
        text = text.replace("Run them with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<script>`.", "Run them with `python3 <skill folder>/../../scripts/<script>`, where `<skill folder>` is the folder holding this SKILL.md.")
        text = text.replace("${CLAUDE_PLUGIN_ROOT}/scripts/", "<skill folder>/../../scripts/")
        # The release reminder is an upstream hook that is not bundled, so the Codex skill must not promise it.
        text = text.replace(" A quiet hook reminds you after a release command; turn it off with `WORK_MAP_SHIP_REMINDER=0`.", "")
    return text


def _git_bytes(room_dir, *args):
    done = subprocess.run(["git", "-C", str(room_dir), *args], capture_output=True)
    if done.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed in {room_dir}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout


def copy_pinned_scripts(room_dir, sha, out):
    """Copy plugin/scripts from the git tree at `sha` (never the working copy) into `out`, replacing it.
    Every copied file is read back and must equal the pinned blob byte for byte, or nothing is replaced."""
    names = [n for n in _git_bytes(room_dir, "ls-tree", "-r", "--name-only", "-z", sha, "plugin/scripts").decode().split("\0") if n and "__pycache__" not in n.split("/")]
    if not names:
        sys.exit(f"{room_dir} has no plugin/scripts at {sha[:7]}")
    stage = Path(tempfile.mkdtemp(prefix="bundle-scripts-"))
    try:
        for name in names:
            blob = _git_bytes(room_dir, "show", f"{sha}:{name}")
            target = stage / Path(name).relative_to("plugin/scripts")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            if target.read_bytes() != blob:
                sys.exit(f"{name}: copied bytes differ from the pinned tree at {sha[:7]}; bundle refused")
        shutil.rmtree(out, ignore_errors=True)  # start clean so files upstream removed do not linger
        shutil.copytree(stage, out)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    make = dict(re.findall(r"^([A-Z_]+)\s*=\s*(\S+)", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M))
    for room in ("antechamber", "scriptorium", "vault-map", "work-map"):
        head = subprocess.run(["git", "-C", str(ROOT / "rooms" / room), "rev-parse", "HEAD"], capture_output=True, text=True)
        pinned = make[room.upper().replace("-", "_") + "_SHA"]
        if head.returncode != 0 or head.stdout.strip() != pinned:
            sys.exit(f"rooms/{room} is not at its pinned commit {pinned[:7]}: delete it and run make get again")
        src = ROOT / "rooms" / room / "plugin" / "skills" / room / "SKILL.md"
        if not src.is_file():
            sys.exit(f"rooms/{room} is missing: run make get first")
        dest = ROOT / "plugin" / "codex-skills" / room / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(codex_text(room, src.read_text(encoding="utf-8")), encoding="utf-8")
        if room == "work-map":  # its writers ship in the bundle, taken from the pinned tree
            copy_pinned_scripts(ROOT / "rooms" / room, pinned, ROOT / "plugin" / "scripts")

    conn = ROOT / "plugin" / "codex.mcp.json"
    data = json.loads(conn.read_text(encoding="utf-8"))
    sha = make["ANTECHAMBER_SHA"]
    args = data["mcpServers"]["antechamber"]["args"]
    data["mcpServers"]["antechamber"]["args"] = [
        re.sub(r"(github\.com/SolanceLab/antechamber)@\S+", r"\1@" + sha, a) for a in args
    ]
    conn.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("plugin-codex refreshed from rooms/ (Antechamber pinned to " + sha[:7] + ")")


if __name__ == "__main__":
    main()
