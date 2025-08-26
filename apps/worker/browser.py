import asyncio, os
from playwright.async_api import async_playwright

_browser_singleton = {"browser": None, "context": None, "page": None}

async def _ensure_page():
    if _browser_singleton["page"]:
        return _browser_singleton["page"]
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()
    _browser_singleton.update({"browser": browser, "context": context, "page": page})
    return page

async def browser_nav(url: str) -> dict:
    page = await _ensure_page()
    await page.goto(url)
    return {"ok": True, "url": url}

async def browser_click(selector: str, by: str = "css", name: str | None = None) -> dict:
    page = await _ensure_page()
    if by == "role" and name:
        await page.get_by_role(selector, name=name).click()
    else:
        await page.click(selector)
    return {"ok": True, "selector": selector}

async def browser_type(selector: str, text: str, press_enter: bool = False) -> dict:
    page = await _ensure_page()
    await page.fill(selector, text)
    if press_enter:
        await page.keyboard.press("Enter")
    return {"ok": True, "selector": selector, "typed": len(text)}

async def browser_download(selector: str, to_dir: str) -> dict:
    page = await _ensure_page()
    async with page.expect_download() as dl_info:
        await page.click(selector)
    download = await dl_info.value
    path = await download.path()
    os.makedirs(to_dir, exist_ok=True)
    saved = os.path.join(to_dir, download.suggested_filename)
    await download.save_as(saved)
    return {"ok": True, "saved": saved}
