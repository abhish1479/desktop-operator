# apps/worker/browser.py
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
import time

from playwright.sync_api import sync_playwright, BrowserContext, Page

PROFILE_ROOT = Path("data/playwright-profiles")
PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path("data/downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
SCREEN_DIR = Path("data/screens")
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

@contextmanager
def _ctx(profile: str = "default", headless: bool = False, accept_downloads: bool = True) -> BrowserContext:
    """
    Persistent Chromium context so logins/cookies stick across calls.
    """
    from playwright.sync_api import Error as PWError  # avoid import error if playwright not installed
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    user_data_dir = PROFILE_ROOT / profile
    user_data_dir.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()
    # launch_persistent_context gives us a Context directly
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        headless=headless,
        accept_downloads=accept_downloads,
        args=["--start-maximized"],
    )
    try:
        yield ctx
    finally:
        try:
            ctx.close()
        except PWError:
            pass
        pw.stop()

def _new_page(ctx: BrowserContext) -> Page:
    page = ctx.new_page()
    page.set_default_navigation_timeout(60_000)
    page.set_default_timeout(60_000)
    return page

# ---------------------------
# Public helpers used by registry.py
# ---------------------------

def browser_nav(url: str, profile: str = "default", headless: bool = False, wait_until: str = "domcontentloaded") -> dict:
    """
    Open (or reuse) a persistent browser profile and navigate to URL.
    """
    with _ctx(profile=profile, headless=headless) as ctx:
        page = _new_page(ctx)
        page.goto(url, wait_until=wait_until)
        ts = int(time.time() * 1000)
        shot = SCREEN_DIR / f"{ts}-nav.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception:
            shot = None
        return {"ok": True, "url": url, "screenshot": str(shot) if shot else None}

def browser_click(selector: str, profile: str = "default", headless: bool = False, wait_after: Optional[str] = "networkidle") -> dict:
    """
    Click an element by CSS/XPath/text selector on the current tab.
    If no page is open in this profile, opens a blank one.
    """
    with _ctx(profile=profile, headless=headless) as ctx:
        page = _new_page(ctx)
        # If no page content loaded yet, just click won't work.
        # Users should navigate first; we keep a no-op guard:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            pass
        page.click(selector)
        if wait_after:
            try:
                page.wait_for_load_state(wait_after, timeout=15_000)
            except Exception:
                pass
        ts = int(time.time() * 1000)
        shot = SCREEN_DIR / f"{ts}-click.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception:
            shot = None
        return {"ok": True, "selector": selector, "screenshot": str(shot) if shot else None}

def browser_type(selector: str, text: str, profile: str = "default", headless: bool = False, clear: bool = False) -> dict:
    """
    Type into an input/textarea matched by selector.
    """
    with _ctx(profile=profile, headless=headless) as ctx:
        page = _new_page(ctx)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            pass
        page.wait_for_selector(selector, timeout=10_000)
        if clear:
            page.fill(selector, "")
        page.type(selector, text, delay=20)
        ts = int(time.time() * 1000)
        shot = SCREEN_DIR / f"{ts}-type.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception:
            shot = None
        return {"ok": True, "selector": selector, "typed": len(text), "screenshot": str(shot) if shot else None}

def browser_download(
    url: Optional[str] = None,
    selector: Optional[str] = None,
    profile: str = "default",
    headless: bool = False,
    download_dir: Optional[str] = None,
    wait_until: str = "domcontentloaded",
) -> dict:
    """
    Download a file either by:
      A) directly visiting a URL that triggers a download, or
      B) clicking a selector that triggers a download on the page.

    Returns the saved file path.
    """
    out_dir = Path(download_dir) if download_dir else DOWNLOAD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    with _ctx(profile=profile, headless=headless, accept_downloads=True) as ctx:
        page = _new_page(ctx)

        # Option A: direct URL navigation triggers download
        if url and selector is None:
            with page.expect_download() as dl_info:
                page.goto(url, wait_until=wait_until)
            download = dl_info.value
        else:
            # Need a page first
            if url:
                page.goto(url, wait_until=wait_until)
            page.wait_for_load_state("domcontentloaded")
            if not selector:
                raise ValueError("browser_download: provide either a direct download URL or a selector to click.")
            page.wait_for_selector(selector, timeout=10_000)
            with page.expect_download() as dl_info:
                page.click(selector)
            download = dl_info.value

        suggested = download.suggested_filename
        target = out_dir / suggested
        download.save_as(str(target))
        return {"ok": True, "path": str(target), "filename": suggested}
    

# --- Compatibility wrappers expected by tools.registry -----------------
def browser_nav_with_profile(url: str, profile: str = "default", headless: bool = False, wait_until: str = "domcontentloaded") -> dict:
    """
    Back-compat: same as browser_nav but with explicit profile arg first.
    """
    return browser_nav(url=url, profile=profile, headless=headless, wait_until=wait_until)

def browser_wait_ms(ms: int | float) -> dict:
    """
    Simple wait/sleep helper used by some scripted flows.
    """
    import time as _time
    dur = max(0.0, float(ms) / 1000.0)
    _time.sleep(dur)
    return {"ok": True, "slept_ms": int(ms)}

