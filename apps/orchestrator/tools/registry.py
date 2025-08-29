from __future__ import annotations
import sys
import asyncio
from typing import Dict, Callable, Awaitable, Any
import difflib

# --- Simple browser solution for Windows ---
BROWSER_METHOD = "none"

if sys.platform == "win32":
    try:
        # Try Selenium first
        from ...worker.browser_selenium import (
            browser_nav_selenium, browser_click_selenium, browser_type_selenium,
            browser_wait_ms_selenium, browser_eval_selenium
        )
        BROWSER_METHOD = "selenium"
        print("Using Selenium for browser automation")
        
        # Map to consistent names
        browser_nav_impl = browser_nav_selenium
        browser_click_impl = browser_click_selenium
        browser_type_impl = browser_type_selenium
        browser_wait_ms_impl = browser_wait_ms_selenium
        browser_eval_impl = browser_eval_selenium
        
    except ImportError:
        # Fallback to system command approach
        BROWSER_METHOD = "system"
        print("Using system commands for browser automation")
        
        import subprocess
        import webbrowser
        
        def browser_nav_system(url: str, **kwargs) -> Dict[str, Any]:
            try:
                webbrowser.open(url)
                return {"ok": True, "url": url, "title": "opened_in_default_browser"}
            except Exception as e:
                return {"ok": False, "error": f"system_nav_error: {e}"}
        
        def browser_click_system(selector: str, **kwargs) -> Dict[str, Any]:
            return {"ok": False, "error": "click_not_supported_in_system_mode"}
        
        def browser_type_system(selector: str, text: str, **kwargs) -> Dict[str, Any]:
            return {"ok": False, "error": "type_not_supported_in_system_mode"}
        
        def browser_wait_ms_system(ms: int = 500, **kwargs) -> Dict[str, Any]:
            import time
            time.sleep(max(ms, 0) / 1000.0)
            return {"ok": True, "waited_ms": ms}
        
        def browser_eval_system(js: str, **kwargs) -> Dict[str, Any]:
            return {"ok": False, "error": "eval_not_supported_in_system_mode"}
        
        browser_nav_impl = browser_nav_system
        browser_click_impl = browser_click_system
        browser_type_impl = browser_type_system
        browser_wait_ms_impl = browser_wait_ms_system
        browser_eval_impl = browser_eval_system
        
else:
    # Non-Windows: try async Playwright
    try:
        from ...worker.browser import (
            browser_nav, browser_click, browser_type, browser_wait_ms, browser_eval
        )
        BROWSER_METHOD = "playwright_async"
        browser_nav_impl = browser_nav
        browser_click_impl = browser_click
        browser_type_impl = browser_type
        browser_wait_ms_impl = browser_wait_ms
        browser_eval_impl = browser_eval
    except ImportError:
        BROWSER_METHOD = "none"
        def browser_error(**kwargs):
            return {"ok": False, "error": "browser_not_available"}
        browser_nav_impl = browser_error
        browser_click_impl = browser_error
        browser_type_impl = browser_error
        browser_wait_ms_impl = browser_error
        browser_eval_impl = browser_error

_PW_BOUND = False
pw_browser_download = None  # type: ignore

def ensure_playwright_bound() -> None:
    global _PW_BOUND, BROWSER_METHOD
    global browser_nav_impl, browser_click_impl, browser_type_impl, browser_wait_ms_impl, browser_eval_impl
    global pw_browser_download
    if _PW_BOUND:
        return
    try:
        from ...worker.browser import (
            browser_nav as pw_browser_nav,
            browser_click as pw_browser_click,
            browser_type as pw_browser_type,
            browser_wait_ms as pw_browser_wait_ms,
            browser_eval as pw_browser_eval,
            browser_download as _pw_browser_download,
        )
        BROWSER_METHOD = "playwright_async"
        browser_nav_impl = pw_browser_nav
        browser_click_impl = pw_browser_click
        browser_type_impl = pw_browser_type
        browser_wait_ms_impl = pw_browser_wait_ms
        browser_eval_impl = pw_browser_eval
        pw_browser_download = _pw_browser_download
        _PW_BOUND = True
    except Exception:
        # Leave as-is; wrappers will continue to use current impls
        pass

# Create async wrappers
async def browser_nav_wrapper(url: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    if BROWSER_METHOD != "playwright_async":
        ensure_playwright_bound()
    if BROWSER_METHOD == "playwright_async":
        return await browser_nav_impl(url, profile, headless)
    else:
        # Run sync version in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, browser_nav_impl, url, profile, headless)

async def browser_click_wrapper(selector: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    if BROWSER_METHOD != "playwright_async":
        ensure_playwright_bound()
    if BROWSER_METHOD == "playwright_async":
        return await browser_click_impl(selector, profile)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, browser_click_impl, selector, profile, headless)

async def browser_type_wrapper(selector: str, text: str, profile: str = "default", 
                              clear: bool = False, press_enter: bool = False, headless: bool = False) -> Dict[str, Any]:
    if BROWSER_METHOD != "playwright_async":
        ensure_playwright_bound()
    if BROWSER_METHOD == "playwright_async":
        return await browser_type_impl(selector, text, profile, clear, press_enter)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, browser_type_impl, selector, text, profile, clear, press_enter, headless)

async def browser_wait_ms_wrapper(ms: int = 500) -> Dict[str, Any]:
    if BROWSER_METHOD != "playwright_async":
        ensure_playwright_bound()
    if BROWSER_METHOD == "playwright_async":
        return await browser_wait_ms_impl(ms)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, browser_wait_ms_impl, ms)

async def browser_eval_wrapper(js: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    if BROWSER_METHOD != "playwright_async":
        ensure_playwright_bound()
    if BROWSER_METHOD == "playwright_async":
        return await browser_eval_impl(js, profile)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, browser_eval_impl, js, profile, headless)

# Stub for browser_download
async def browser_download_stub(**kwargs) -> Dict[str, Any]:
    return {"ok": False, "error": f"download_not_available_in_{BROWSER_METHOD}_mode"}

async def browser_download_wrapper(**kwargs) -> Dict[str, Any]:
    if BROWSER_METHOD != "playwright_async":
        ensure_playwright_bound()
    if BROWSER_METHOD == "playwright_async" and pw_browser_download:
        return await pw_browser_download(**kwargs)
    return await browser_download_stub(**kwargs)

# Import other modules
from ...worker.fs import fs_read, fs_write, fs_move, fs_copy, fs_delete, fs_listdir
from ...worker.terminal import terminal_run
from ...worker.pkg import pkg_install, pkg_uninstall, pkg_ensure
from ...worker.http_tool import http_request
from ...worker.data_utils import csv_read, csv_write, json_read, json_write
from ...worker.ui import ui_focus, ui_click, ui_type, ui_menu_select, ui_wait, ui_shortcut
from ...worker.vscode_bridge import vscode_open, vscode_save_all, vscode_get_diagnostics, vscode_install_extension

# Optional multi-step browser executor
try:
    from ...worker.browser_actions import browser_execute as browser_execute_impl
except Exception:
    async def browser_execute_impl(**kwargs) -> dict:
        return {"ok": False, "error": f"browser_execute_not_available_in_{BROWSER_METHOD}_mode"}

try:
    from ...worker.app_launch import launch
except Exception:
    def launch(name: str) -> dict:
        return {"ok": False, "error": "app_launch_not_implemented"}

# Register WhatsApp Desktop chat tool via lazy import wrapper to avoid import-time failures
import asyncio
async def whatsapp_desktop_chat(**kwargs):  # type: ignore
    try:
        # Lazy import so missing deps (e.g., uiautomation) don't break registry import
        from ...worker.skills.whatsapp_desktop_chat import run_desktop_chat
        import uiautomation as auto  # ensure available here for initializer
    except ImportError as e:
        return {"ok": False, "error": f"whatsapp_desktop_chat_dep_missing: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"whatsapp_desktop_chat_import_error: {e}"}

    def _invoke() -> dict:
        # Initialize UIAutomation/COM in this thread
        try:
            with auto.UIAutomationInitializerInThread():
                return run_desktop_chat(**kwargs)
        except Exception as e:
            return {"ok": False, "error": f"whatsapp_desktop_chat_runtime_error: {e}"}

    loop = asyncio.get_event_loop()
    try:
        # run_desktop_chat is synchronous; run in thread with proper UIA init
        return await loop.run_in_executor(None, _invoke)
    except Exception as e:
        return {"ok": False, "error": f"whatsapp_desktop_chat_runtime_error: {e}"}

# TOOL REGISTRY
TOOL_REGISTRY: Dict[str, Callable[..., Awaitable[dict]] | Callable[..., dict]] = {
    # Browser (using wrappers)
    "browser_nav": browser_nav_wrapper,
    "browser_type": browser_type_wrapper,
    "browser_click": browser_click_wrapper,
    "browser_wait_ms": browser_wait_ms_wrapper,
    "browser_eval": browser_eval_wrapper,
    "browser_download": browser_download_wrapper,
    "browser_execute": browser_execute_impl,
    
    # Filesystem
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_move": fs_move,
    "fs_copy": fs_copy,
    "fs_delete": fs_delete,
    "fs_listdir": fs_listdir,

    # Terminal / Packages
    "terminal_run": terminal_run,
    "pkg_install": pkg_install,
    "pkg_uninstall": pkg_uninstall,
    "pkg_ensure": pkg_ensure,

    # HTTP / Data
    "http_request": http_request,
    "data_csv.read": csv_read,
    "data_csv.write": csv_write,
    "data_json.read": json_read,
    "data_json.write": json_write,

    # Desktop UI
    "ui_focus": ui_focus,
    "ui_click": ui_click,
    "ui_type": ui_type,
    "ui_menu_select": ui_menu_select,
    "ui_wait": ui_wait,
    "ui_shortcut": ui_shortcut,

    # VS Code
    "vscode_open": vscode_open,
    "vscode_save_all": vscode_save_all,
    "vscode_get_diagnostics": vscode_get_diagnostics,
    "vscode_install_extension": vscode_install_extension,

    # App launch
    "app_launch": launch,

    # WhatsApp Desktop chat (lazy wrapper)
    "whatsapp_desktop_chat": whatsapp_desktop_chat,
}

print(f"Browser automation method: {BROWSER_METHOD}")

# ---- Aliases for dot/underscore variants and inline-plan names ----
TOOL_REGISTRY.update({
    # inline/dot style
    "terminal.run": TOOL_REGISTRY.get("terminal_run"),
    "fs.write": TOOL_REGISTRY.get("fs_write"),
    "fs.move": TOOL_REGISTRY.get("fs_move"),
    "fs.copy": TOOL_REGISTRY.get("fs_copy"),
    "fs.delete": TOOL_REGISTRY.get("fs_delete"),
    "fs.listdir": TOOL_REGISTRY.get("fs_listdir"),
    "browser.execute": TOOL_REGISTRY.get("browser_execute"),
    # underscore data tool names used in LLM specs
    "data_csv_read": TOOL_REGISTRY.get("data_csv.read"),
    "data_csv_write": TOOL_REGISTRY.get("data_csv.write"),
    "data_json_read": TOOL_REGISTRY.get("data_json.read"),
    "data_json_write": TOOL_REGISTRY.get("data_json.write"),
    # WhatsApp friendly aliases
    "whatsapp_send": TOOL_REGISTRY.get("whatsapp_desktop_chat"),
    "whatsapp.chat": TOOL_REGISTRY.get("whatsapp_desktop_chat"),
})

# --- Robust tool lookup: case-insensitive and fuzzy matching ---
def get_tool(tool_name: str, registry: dict) -> tuple[object, str] | tuple[None, None]:
    """
    Returns (tool_callable, matched_name) or (None, None) if not found.
    Tries exact match (case-insensitive), then fuzzy match.
    """
    tool_name_lc = tool_name.lower()
    # Ensure registry keys are lowercase
    registry_lc = {k.lower(): v for k, v in registry.items()}
    # Exact match
    if tool_name_lc in registry_lc:
        return registry_lc[tool_name_lc], tool_name_lc
    # Fuzzy match
    close = difflib.get_close_matches(tool_name_lc, registry_lc.keys(), n=1, cutoff=0.7)
    if close:
        return registry_lc[close[0]], close[0]
    return None, None

# --- Ensure TOOL_REGISTRY keys are lowercase for robust matching ---
TOOL_REGISTRY = {k.lower(): v for k, v in TOOL_REGISTRY.items()}

# Usage example (in orchestrator):
#   tool, matched_name = get_tool(tool_name, TOOL_REGISTRY)
#   if not tool:
#       ... handle unknown tool ...