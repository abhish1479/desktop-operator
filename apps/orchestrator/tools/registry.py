from typing import Dict, Callable, Awaitable

from ...worker.filesystem import write_text, move_path, listdir_path
from ...worker.terminal import run_cmd
from ...worker.vscode_bridge import vscode_open, vscode_save_all, vscode_get_diagnostics
from ...worker.browser import browser_nav, browser_click, browser_type, browser_download
from ...worker.ui_automation import window_focus, ui_click, ui_type, ui_menu_select

from ...worker.app_launch import launch as app_launch_launch

from ..policy import policy

def _ensure_path_allowed(path: str):
    ok, reason = policy.sandbox_guard(path)
    if not ok:
        raise PermissionError(reason)

def _ensure_exec_allowed(bin_name: str, args: list[str]):
    ok, reason = policy.is_exec_allowed(bin_name, args)
    if not ok:
        raise PermissionError(reason)

async def app_launch(name: str) -> dict:
    return app_launch_launch(name)

async def fs_write(path: str, content: str) -> dict:
    return write_text(path, content)

async def fs_move(src: str, dst: str) -> dict:
    return move_path(src, dst)

async def fs_listdir(path: str) -> dict:
    return listdir_path(path)

async def terminal_run(cmd: str, shell: str = "powershell", timeout_sec: int = 120) -> dict:
    return run_cmd(cmd, shell, timeout_sec)

async def vscode_open_wrapper(path: str, line: int | None = None) -> dict:
    return vscode_open(path, line)

async def vscode_save_all_wrapper() -> dict:
    return vscode_save_all()

async def vscode_get_diagnostics_wrapper() -> dict:
    return vscode_get_diagnostics()

async def browser_nav_wrapper(url: str) -> dict:
    return await browser_nav(url)

async def browser_click_wrapper(selector: str, by: str = "css", name: str | None = None) -> dict:
    return await browser_click(selector, by, name)

async def browser_type_wrapper(selector: str, text: str, press_enter: bool = False) -> dict:
    return await browser_type(selector, text, press_enter)

async def browser_download_wrapper(selector: str, to_dir: str) -> dict:
    return await browser_download(selector, to_dir)
async def ui_focus(title_re: str) -> dict:
    return window_focus(title_re)

async def ui_click_wrapper(name: str, control_type: str="Button") -> dict:
    return ui_click(name, control_type)

async def ui_type_wrapper(text: str) -> dict:
    return ui_type(text)

async def ui_menu_wrapper(path: str) -> dict:
    return ui_menu_select(path)

from ...worker.browser import browser_nav_with_profile, browser_wait_ms
async def browser_nav_profile(url: str, user_data_dir: str) -> dict: 
    return await browser_nav_with_profile(url, user_data_dir)
async def browser_wait(ms: int=60000) -> dict: 
    return await browser_wait_ms(ms)


TOOL_REGISTRY: Dict[str, Callable[..., Awaitable[dict]]] = {
    "fs_write": fs_write,
    "fs_move": fs_move,
    "fs_listdir": fs_listdir,
    "terminal_run": terminal_run,
    "vscode_open": vscode_open_wrapper,
    "vscode_save_all": vscode_save_all_wrapper,
    "vscode_get_diagnostics": vscode_get_diagnostics_wrapper,
    "browser_nav": browser_nav_wrapper,
    "browser_click": browser_click_wrapper,
    "browser_type": browser_type_wrapper,
    "browser_download": browser_download_wrapper,
    "browser_nav_profile": browser_nav_profile,
    "browser_wait": browser_wait,
    "ui_focus": ui_focus,
    "ui_click": ui_click_wrapper,
    "ui_type": ui_type_wrapper,
    "ui_menu_select": ui_menu_wrapper,
    "app_launch": app_launch,
    

}
