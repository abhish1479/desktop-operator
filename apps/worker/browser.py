import asyncio, os
# apps/worker/browser.py  (sync API wrapped for async callers)
import concurrent.futures
from functools import lru_cache
from playwright.sync_api import sync_playwright

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

@lru_cache(maxsize=1)
def _get_playwright():
    # Starting sync Playwright once; reused in the thread
    pw = sync_playwright().start()
    ctx = pw.chromium.launch(headless=False)
    page = ctx.new_page()
    return pw, ctx, page

def _nav(url: str) -> dict:
    try:
        pw, ctx, page = _get_playwright()
        page.goto(url)
        return {"ok": True, "url": url, "title": page.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _click(selector: str, name: str | None = None) -> dict:
    try:
        _, _, page = _get_playwright()
        page.click(selector)
        return {"ok": True, "selector": selector, "name": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _type(selector: str, text: str, press_enter: bool = False) -> dict:
    try:
        _, _, page = _get_playwright()
        page.fill(selector, "")  # ensure clean
        page.type(selector, text)
        if press_enter:
            page.keyboard.press("Enter")
        return {"ok": True, "selector": selector, "typed": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---- async wrappers used by tools.registry ----
async def browser_nav(url: str) -> dict:
    return await asyncio.get_running_loop().run_in_executor(_executor, _nav, url)

async def browser_click(selector: str, by: str = "css", name: str | None = None) -> dict:
    return await asyncio.get_running_loop().run_in_executor(_executor, _click, selector, name)

async def browser_type(selector: str, text: str, press_enter: bool = False) -> dict:
    return await asyncio.get_running_loop().run_in_executor(_executor, _type, selector, text, press_enter)
