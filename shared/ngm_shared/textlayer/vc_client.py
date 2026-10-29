"""Klient VectorCraftu přes MCP (stdio, JSON-RPC po řádcích).

VectorCraft (open-source klon Illustratoru, `vectorcraft-cli.exe mcp --headless`) je
samostatná aplikace mimo repo. Cesta se hledá v tomto pořadí:

1. `NGROBOT_VECTORCRAFT_CLI` — přímo cesta k `vectorcraft-cli.exe`,
2. `CRAFT_HOME` — složka s podsložkou `vectorcraft/` (stejná proměnná jako v `.mcp.json`),
3. výchozí `C:/Users/stock/Tools/Craft`.

Každé volání má časový limit. Když server spadne nebo neodpoví, vyletí
`VectorCraftError` — skládání raději skončí hlasitě, než aby nechalo
polovičatý soubor tvářící se jako hotový.

Kopie z NG-ROBOT `ng_vector_labels/vc_client.py`, commit f27580e9534a408e35b153d06376e4d34697b092
(2026-10-29, GRAFIK fáze 3). Opravy z NG-ROBOT přenášej diffem originálu od tohoto commitu:
`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/vc_client.py`.
Změny proti originálu: relace drží zámek těžké práce `ngm_shared.heavy_lock` (druh
`vectorcraft`) od startu do `close()`; `lock_owner=None` ho vypne pro volajícího,
který zámek už drží. Jméno klienta v MCP `ngm-shared-textlayer`.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from ngm_shared.heavy_lock import LOCK_PATH, HeavyLock

logger = logging.getLogger(__name__)

DEFAULT_CRAFT_HOME = "C:/Users/stock/Tools/Craft"
CALL_TIMEOUT_S = 180.0
LOCK_WAIT_S = 1800.0


class VectorCraftError(RuntimeError):
    """VectorCraft chybí, spadl nebo vrátil chybu."""


def find_cli() -> Optional[Path]:
    """Cesta k `vectorcraft-cli.exe`, nebo None, když není nainstalovaný."""
    direct = os.environ.get("NGROBOT_VECTORCRAFT_CLI")
    if direct:
        p = Path(direct)
        return p if p.is_file() else None
    home = Path(os.environ.get("CRAFT_HOME") or DEFAULT_CRAFT_HOME)
    p = home / "vectorcraft" / "vectorcraft-cli.exe"
    return p if p.is_file() else None


def find_desktop_app() -> Optional[Path]:
    """Okenní aplikace VectorCraft (otevření `.vectorcraft` pro ruční úpravy)."""
    cli = find_cli()
    if cli is None:
        return None
    app = cli.with_name("vectorcraft.exe")
    return app if app.is_file() else None


class VectorCraft:
    """Jedna headless relace VectorCraftu. Použití: `with VectorCraft() as vc: vc.tool(...)`."""

    def __init__(self, cli: Optional[Path] = None, timeout: float = CALL_TIMEOUT_S, *,
                 lock_owner: Optional[str] = "ngm-shared", caller: Optional[str] = None,
                 lock_wait_s: float = LOCK_WAIT_S, lock_path: Path = LOCK_PATH):
        cli = cli or find_cli()
        if cli is None:
            raise VectorCraftError(
                "VectorCraft není nainstalovaný (nastavte CRAFT_HOME nebo NGROBOT_VECTORCRAFT_CLI)")
        self.timeout = timeout
        # VectorCraft bere až ~1,2 GB paměti grafiky: běží jen pod zámkem těžké práce (HeavyBusy po lock_wait_s)
        self._lock = HeavyLock(lock_path, lock_owner) if lock_owner else None
        if self._lock:
            self._lock.acquire(lock_wait_s, "vectorcraft", caller)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._p = subprocess.Popen(
                [str(cli), "mcp", "--headless"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=flags)
        except OSError:
            if self._lock:
                self._lock.release()
            raise
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._n = 0
        try:
            init = self._rpc("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "ngm-shared-textlayer", "version": "1"}})
        except VectorCraftError:
            self.close()        # proces i zámek, jinak by zámek visel do konce procesu volajícího
            raise
        self.server = init.get("result", {}).get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _pump(self) -> None:
        for line in self._p.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, msg: dict) -> None:
        try:
            self._p.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self._p.stdin.flush()
        except OSError as e:
            raise VectorCraftError(f"VectorCraft neběží: {e}") from e

    def _rpc(self, method: str, params: dict) -> dict:
        self._n += 1
        self._send({"jsonrpc": "2.0", "id": self._n, "method": method, "params": params})
        while True:
            try:
                line = self._lines.get(timeout=self.timeout)
            except queue.Empty:
                raise VectorCraftError(f"VectorCraft neodpověděl do {self.timeout:.0f} s ({method})") from None
            if line is None:
                raise VectorCraftError(f"VectorCraft se ukončil ({method})")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == self._n:
                return msg

    def tool(self, name: str, **args: Any) -> Any:
        """Zavolá MCP nástroj; vrací rozparsovaný JSON (nebo text)."""
        msg = self._rpc("tools/call", {"name": name, "arguments": args})
        if "error" in msg:
            raise VectorCraftError(f"{name}: {msg['error']}")
        res = msg.get("result") or {}
        txt = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        if res.get("isError"):
            raise VectorCraftError(f"{name}: {txt[:500]}")
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return txt

    def cmd(self, command: str, **params: Any) -> Any:
        """Příkaz z katalogu VectorCraftu (`vectorcraft-cli commands`) přes `run_command`."""
        return self.tool("run_command", command=command, params=params)

    def close(self) -> None:
        try:
            if self._p.stdin and not self._p.stdin.closed:
                self._p.stdin.close()
            self._p.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            self._p.kill()
        finally:
            if self._lock:
                self._lock.release()
                self._lock = None

    def __enter__(self) -> "VectorCraft":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
