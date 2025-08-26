from typing import Dict, Callable, Awaitable

from ...worker.filesystem import write_text, move_path, listdir_path
from ...worker.terminal import run_cmd
from ...worker.vscode_bridge import vscode_open, vscode_save_all, vscode_get_diagnostics
from ...worker.browser import browser_nav, browser_click, browser_type, browser_download

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
}
