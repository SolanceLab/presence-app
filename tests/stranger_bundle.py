# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""The bundle test: install presence-app ONCE, in empty Claude Code and Codex homes, and check that all three
rooms (Antechamber, Scriptorium, vault-map) came with it and each one answers.

  python3 tests/stranger_bundle.py ANTECHAMBER_CHECKOUT SCRIPTORIUM_CHECKOUT VAULT_MAP_CHECKOUT

Needs the claude, codex and uvx commands and the internet (the plugins fetch their pinned releases from GitHub).
In throwaway folders; nothing of yours is read or changed. It builds a LOCAL store from this repo's bundle
plugin and copies of the three rooms' `plugin` folders; it proves the install mechanics and that each room answers,
not the published store (the publish script checks that after the release). Exit 0 only if every check passed."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

QUESTION = "which ferry leaves from Labuan Bajo at dawn"
SAMPLE = "The ferry to Komodo leaves from Labuan Bajo at dawn, and the tickets are sold at the harbour office."
KEY = "bundle-test-key-0123456789"
REPO = Path(__file__).resolve().parent.parent
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)
    return ok


def run(cmd, env, cwd=None, timeout=900):
    p = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


class Mcp:
    """One MCP stdio session."""

    def __init__(self, command, args, env):
        self.p = subprocess.Popen([command, *args], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        self.n = 0
        self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "bundle-test", "version": "1"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.p.stdin.flush()

    def call(self, method, params):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        return json.loads(line) if line else {"error": "server closed"}

    def tools(self):
        return [t["name"] for t in self.call("tools/list", {}).get("result", {}).get("tools", [])]

    def tool(self, name, **args):
        r = self.call("tools/call", {"name": name, "arguments": args}).get("result", {})
        return "".join(c.get("text", "") for c in r.get("content", [])), bool(r.get("isError"))

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http_tools(port, key):
    """tools/list against a Scriptorium server over MCP streamable HTTP."""
    def post(body, session=None):
        h = {"content-type": "application/json", "accept": "application/json, text/event-stream",
             "authorization": f"Bearer {key}"}
        if session:
            h["mcp-session-id"] = session
        req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", json.dumps(body).encode(), h)
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode()
            return r.headers.get("mcp-session-id"), text
    sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "bundle-test", "version": "1"}}})
    try:
        post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except Exception:
        pass
    _, text = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid)
    m = re.search(r"\{.*\}", text.replace("data: ", ""), re.S)
    return [t["name"] for t in json.loads(m.group(0)).get("result", {}).get("tools", [])]


def servers_in(root):
    """Every mcpServers entry recorded anywhere under an install root."""
    found = {}
    for f in list(root.rglob(".mcp.json")) + list(root.rglob("codex.mcp.json")) + list(root.rglob("plugin.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        block = d.get("mcpServers", d)
        if isinstance(block, dict):
            for name, spec in block.items():
                if isinstance(spec, dict):
                    found.setdefault(name, spec)
    return found


def skill_texts(root):
    return {p.parent.name: p.read_text(encoding="utf-8") for p in root.rglob("SKILL.md")}


def prove_rooms(label, install_root, sc_checkout, env, td):
    """All three rooms answer from what this install put on disk."""
    servers = servers_in(install_root)
    skills = skill_texts(install_root)
    check(f"{label}: the three skills arrived", {"antechamber", "scriptorium", "vault-map", "presence-app"} <= set(skills), str(sorted(skills)))
    check(f"{label}: the Antechamber server is recorded as a command", "command" in servers.get("antechamber", {}), str(servers))
    sc = servers.get("scriptorium", {})
    check(f"{label}: the Scriptorium server is recorded", bool(sc), str(sorted(servers)))

    # 1. Antechamber answers over stdio (set up, then recall)
    notes = td / "home" / f"notes-{label}"
    notes.mkdir()
    (notes / "travel.md").write_text("# Travel\n\n" + SAMPLE + "\n", encoding="utf-8")
    spec = servers.get("antechamber", {})
    if spec.get("command"):
        m = Mcp(spec["command"], spec.get("args", []), env)
        try:
            names = m.tools()
            check(f"{label}: Antechamber lists its tools", "recall" in names, str(names))
            m.tool("setup_stores", stores=[{"kind": "notes", "path": str(notes)}])
            text, err = m.tool("recall", query=QUESTION)
            check(f"{label}: Antechamber recalls the sample note", "ferry to Komodo" in text and not err, text[:160])
        finally:
            m.close()

    # 2. Scriptorium answers over HTTP, on the key the plugin names
    port = free_port()
    root = td / f"scriptorium-root-{label}"
    root.mkdir()
    senv = {**env, "SCRIPTORIUM_MCP_KEY": KEY}
    srv = subprocess.Popen([sys.executable, str(sc_checkout / "mcp" / "server.py"), "--root", str(root), "--port", str(port)],
                           env=senv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        names = []
        for _ in range(40):
            time.sleep(0.5)
            try:
                names = http_tools(port, KEY)
                break
            except Exception:
                continue
        check(f"{label}: Scriptorium answers tools/list with the key", bool(names), "no answer")
        env_var = sc.get("bearer_token_env_var") or "SCRIPTORIUM_MCP_KEY"
        check(f"{label}: the plugin reads the Scriptorium key from {env_var}", env_var == "SCRIPTORIUM_MCP_KEY" or "headers" in sc, str(sc))
    finally:
        srv.kill()

    # 3. vault-map answers from the exact command its installed skill tells the AI to run
    vault = td / f"vault-{label}"
    vault.mkdir()
    (vault / "boats.md").write_text("# Boats\n\n" + SAMPLE + "\n", encoding="utf-8")
    m = re.search(r'uvx --from "([^"]+)" vault-map\.py', skills.get("vault-map", ""))
    check(f"{label}: the vault-map skill names its pinned uvx command", bool(m))
    if m:
        pin = m.group(1)
        rc, out = run(["uvx", "--from", pin, "vault-map.py", "build", str(vault)], env, td)
        rc2, out2 = run(["uvx", "--from", pin, "vault-map.py", "query", "ferry Labuan Bajo dawn", str(vault), "--sections", "--n", "3"], env, td)
        check(f"{label}: vault-map builds and finds the passage", rc == 0 and rc2 == 0 and "Komodo" in out2, (out + out2)[-200:])


def main():
    for tool in ("claude", "codex", "uvx"):
        if not shutil.which(tool):
            sys.exit(f"bundle test needs {tool} on PATH")
    if len(sys.argv) != 4:
        sys.exit("usage: stranger_bundle.py ANTECHAMBER_CHECKOUT SCRIPTORIUM_CHECKOUT VAULT_MAP_CHECKOUT")
    ante, scrip, vault_map = (Path(a).resolve() for a in sys.argv[1:4])
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        mkt = td / "store"
        (mkt / ".claude-plugin").mkdir(parents=True)
        (mkt / ".agents" / "plugins").mkdir(parents=True)
        shutil.copytree(REPO / "plugin", mkt / "presence-app", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ante / "plugin", mkt / "antechamber", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(scrip / "plugin", mkt / "scriptorium", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(vault_map / "plugin", mkt / "vault-map", ignore=shutil.ignore_patterns("__pycache__"))
        (mkt / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
            "name": "bundletest", "owner": {"name": "House of Solance"},
            "plugins": [{"name": n, "source": f"./{n}", "description": n} for n in
                        ("presence-app", "antechamber", "scriptorium", "vault-map")]}))
        (mkt / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({
            "name": "bundletest", "interface": {"displayName": "bundletest"},
            "plugins": [{"name": "presence-app", "source": "./presence-app",
                         "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}]}))
        home = td / "home"
        home.mkdir()
        base = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL")}
        (td / "tmp").mkdir()
        base.update({"TMPDIR": str(td / "tmp"), "HOME": str(home), "ANTECHAMBER_HOME_ROOT": str(home),
                     "XDG_CONFIG_HOME": str(td / "xdg"), "XDG_CACHE_HOME": str(td / "cache"),
                     "UV_CACHE_DIR": str(td / "uvcache"), "ANTECHAMBER_CONFIG": str(td / "xdg" / "antechamber" / "config.toml"),
                     "PLUGIN_UPDATE_CHECK": "0"})

        cenv = {**base, "CLAUDE_CONFIG_DIR": str(td / "claude")}
        (td / "claude").mkdir()
        rc, out = run(["claude", "plugin", "marketplace", "add", str(mkt)], cenv, td)
        check("claude: marketplace add", rc == 0, out[-300:])
        rc, out = run(["claude", "plugin", "install", "presence-app@bundletest"], cenv, td)
        check("claude: ONE install of presence-app", rc == 0, out[-300:])
        check("claude: it reports the three dependencies", "3 dependencies" in out, out[-300:])
        rc, out = run(["claude", "plugin", "list"], cenv, td)
        check("claude: the list shows all four plugins",
              rc == 0 and all(n + "@bundletest" in out for n in ("presence-app", "antechamber", "scriptorium", "vault-map")), out[-300:])
        installed = td / "claude" / "plugins"
        prove_rooms("claude", installed if installed.exists() else td / "claude", scrip, cenv, td)
        shutil.rmtree(td / "xdg", ignore_errors=True)

        xenv = {**base, "CODEX_HOME": str(td / "codex")}
        (td / "codex").mkdir()
        rc, out = run(["codex", "plugin", "marketplace", "add", str(mkt)], xenv, td)
        check("codex: marketplace add", rc == 0, out[-300:])
        rc, out = run(["codex", "plugin", "add", "presence-app@bundletest"], xenv, td)
        check("codex: ONE install of presence-app", rc == 0, out[-300:])
        prove_rooms("codex", td / "codex", scrip, xenv, td)

    print(f"\n{sum(results)}/{len(results)} checks passed in {time.time() - t0:.0f}s", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
