from __future__ import annotations
from typing import Dict, Callable, Awaitable, Any

# --- Browser (async Playwright) ---
from ...worker.browser import (
    browser_nav,
    browser_click,
    browser_type,
    browser_wait_ms,
    browser_eval,
    browser_download,
)
from ...worker.browser_actions import browser_execute

# --- Filesystem ---
from ...worker.fs import (
    fs_read, fs_write, fs_move, fs_copy, fs_delete, fs_listdir
)

# --- Terminal (async) ---
from ...worker.terminal import terminal_run

# --- Packages (winget/choco wrappers) ---
from ...worker.pkg import pkg_install, pkg_uninstall, pkg_ensure

# --- HTTP client ---
from ...worker.http_tool import http_request

# --- Data utils ---
from ...worker.data_utils import csv_read, csv_write, json_read, json_write

# --- Desktop UI (Windows) ---
from ...worker.ui import (
    ui_focus, ui_click, ui_type, ui_menu_select, ui_wait, ui_shortcut
)

# --- VS Code bridge ---
from ...worker.vscode_bridge import (
    vscode_open,
    vscode_save_all,
    vscode_get_diagnostics,
    vscode_install_extension,
)

# --- App launch (optional, if present) ---
try:
    from ...worker.app_launch import launch
except Exception:
    # If you don't have worker/apps.py yet, you can add it later; this keeps registry import-safe.
    def app_launch(name: str) -> dict:
        return {"ok": False, "error": "app_launch_not_implemented"}

# ----------------------------- TOOL REGISTRY -----------------------------
# Mix of async (Playwright/terminal/pkg) and sync (fs/ui/http/data/vscode)
# Your dispatcher already awaits async callables and threads sync ones.

TOOL_REGISTRY: Dict[str, Callable[..., Awaitable[dict]] | Callable[..., dict]] = {
    # Browser (canonical async names)
    "browser.nav": browser_nav,
    "browser.type": browser_type,
    "browser.click": browser_click,
    "browser.wait_ms": browser_wait_ms,
    "browser.eval": browser_eval,
    "browser.download": browser_download,
    "browser.execute": browser_execute,

    # Filesystem
    "fs.read": fs_read,
    "fs.write": fs_write,
    "fs.move": fs_move,
    "fs.copy": fs_copy,
    "fs.delete": fs_delete,
    "fs.listdir": fs_listdir,

    # Terminal / Packages
    "terminal.run": terminal_run,
    "pkg.install": pkg_install,
    "pkg.uninstall": pkg_uninstall,
    "pkg.ensure": pkg_ensure,

    # HTTP / Data
    "http.request": http_request,
    "data.csv.read": csv_read,
    "data.csv.write": csv_write,
    "data.json.read": json_read,
    "data.json.write": json_write,

    # Desktop UI
    "ui.focus": ui_focus,
    "ui.click": ui_click,
    "ui.type": ui_type,
    "ui.menu_select": ui_menu_select,
    "ui.wait": ui_wait,
    "ui.shortcut": ui_shortcut,

    # VS Code
    "vscode.open": vscode_open,
    "vscode.save_all": vscode_save_all,
    "vscode.get_diagnostics": vscode_get_diagnostics,
    "vscode.install_extension": vscode_install_extension,  # <-- add this line

    # App launch
    "app.launch": launch,
}

# ---- Optional legacy aliases (ONLY if old prompts depend on them) ----
TOOL_REGISTRY.update({
    "browser_nav": browser_nav,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_wait_ms": browser_wait_ms,
    "browser_eval": browser_eval,
    "browser_download": browser_download,
})
