# apps/orchestrator/main.py
from __future__ import annotations

import sys
import time
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger

from .middleware.logging import JsonLoggerMiddleware
from .metrics import router as metrics_router
from .skills_router import router as skills_router
from .ui_router import router as ui_router
from .journal import begin, undo
from .llm import LLM
from .tools.registry import TOOL_REGISTRY
from .policy import policy  # expanded guardrails loader you added

from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends
from pydantic import BaseModel

class TaskRunCompat(BaseModel):
    # any of these can carry your natural instruction
    goal: Optional[str] = None
    prompt: Optional[str] = None
    text: Optional[str] = None
    instruction: Optional[str] = None

    dry_run: Optional[bool] = True
    budget_rupees: Optional[int] = None
    options: Optional[Dict[str, Any]] = None  # profile, max_steps, allowed_tools, blocked_tools, etc.

def _normalize_goal(req: TaskRunCompat) -> str:
    return (req.goal or req.prompt or req.text or req.instruction or "").strip()

# tiny parser for inline hints in your natural sentence
import re
def _inline_hints(goal: str):
    opts: Dict[str, Any] = {}
    dry = None
    m = re.search(r"profile\s*[:=]\s*([A-Za-z0-9_.\-]+)", goal, re.I)
    if m: opts["profile"] = m.group(1)
    m = re.search(r"max\s*steps\s*[:=]?\s*(\d{1,3})", goal, re.I)
    if m: opts["max_steps"] = int(m.group(1))
    if re.search(r"\bdry\s*run\s*off\b", goal, re.I): dry = False
    if re.search(r"\bdry\s*run\s*on\b", goal, re.I):  dry = True
    return dry, opts


# --- Windows event loop policy (optional; remove if not needed) ---
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# -------- Lifespan: init/teardown singletons cleanly (no @on_event) --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = LLM()  # create once
    logger.info("LLM initialized")
    try:
        yield
    finally:
        llm = getattr(app.state, "llm", None)
        if llm and hasattr(llm, "aclose"):
            try:
                await llm.aclose()
            except Exception as e:
                logger.warning(f"LLM aclose failed: {e}")
        elif llm and hasattr(llm, "close"):
            try:
                llm.close()
            except Exception as e:
                logger.warning(f"LLM close failed: {e}")
        logger.info("Shutdown complete")

app = FastAPI(title="Desktop Operator Orchestrator", version="0.1.0", lifespan=lifespan)
app.add_middleware(JsonLoggerMiddleware)

# ----------------------------- Dependencies -----------------------------
def get_llm(request: Request) -> LLM:
    return request.app.state.llm

# ------------------------------- Routers --------------------------------
app.include_router(metrics_router)
app.include_router(skills_router)       # /skills/* endpoints from your skills_router
app.include_router(ui_router)           # serves /ui via ui_router

# ------------------------------- Basics ---------------------------------
@app.get("/")
def root():
    return {"ok": True, "service": "desktop-operator"}

# Inline UI fallback (works even if ui_router wasn’t included for some reason)
@app.get("/ui", response_class=HTMLResponse)
def ui():
    html_path = Path(__file__).with_name("ui.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))

# Quiet the favicon 404
@app.get("/favicon.ico")
def favicon():
    return HTMLResponse("", media_type="image/x-icon")

# ----------------------------- Journal API ------------------------------
@app.post("/tasks/op/begin")
def begin_op(operation: str, meta: dict):
    return {"op_id": begin(operation, meta)}

@app.post("/tasks/op/undo")
def undo_op(op_id: str, dry_run: bool = True):
    return {"op_id": op_id, "actions": undo(op_id, dry_run=dry_run)}

# ------------------------------- Health ---------------------------------
@app.get("/healthz")
async def healthz():
    return {"ok": True}

# ---------------------------- Task Runner API ---------------------------
class TaskRequest(BaseModel):
    goal: str
    budget_rupees: Optional[int] = None
    dry_run: bool = True
    options: Optional[Dict[str, Any]] = None  # profile/max_steps etc. from UI

@app.post("/tasks/run")
async def run_task(req: TaskRunCompat, llm: LLM = Depends(get_llm)):
    """
    Natural-language agent loop:
      - normalizes goal from goal/prompt/text/instruction
      - parses inline hints (profile:, max steps, dry run on/off)
      - LLM chooses tools; policy enforces limits/timeouts
    """
    goal = _normalize_goal(req)
    if not goal:
        raise HTTPException(status_code=400, detail="missing goal/prompt/text/instruction")

    # Merge inline hints into options
    hinted_dry, hinted_opts = _inline_hints(goal)
    options = dict(req.options or {})
    options.update(hinted_opts)

    # Guardrail defaults
    defaults = policy.defaults() or {}
    max_steps = int(options.get("max_steps", defaults.get("max_total_steps", 40)))
    per_tool_runtime_sec = int(defaults.get("max_tool_runtime_sec", 120))
    overall_time_budget = max_steps * per_tool_runtime_sec

    # Steering gates
    allowed = set(options.get("allowed_tools", []))
    blocked = set(options.get("blocked_tools", []))

    # Dry run resolution (inline hint wins)
    dry_run = hinted_dry if hinted_dry is not None else (True if req.dry_run is None else bool(req.dry_run))

    start_ts = time.time()
    steps: list[dict] = []

    # Bootstrap conversation/context per your LLM API
    try:
        messages = llm.bootstrap(goal, dry_run, req.budget_rupees)
    except Exception as e:
        logger.exception("LLM bootstrap failed")
        return {"ok": False, "error": f"llm_bootstrap_failed: {e}"}

    for i in range(max_steps):
        # time budget check
        if time.time() - start_ts > overall_time_budget:
            logger.warning("Time budget exceeded; stopping.")
            break

        # Ask LLM what to do next
        try:
            call = llm.next_tool_call(messages)
        except Exception as e:
            logger.exception("LLM next_tool_call failed")
            return {"ok": False, "error": f"llm_next_tool_call_failed: {e}"}

        if not call:
            logger.info("No tool call returned, ending.")
            break

        tool_name = call.get("name")
        args = call.get("arguments", {}) or {}
        logger.info(f"[step {i+1}/{max_steps}] {tool_name}({args})")

        # Steering: allow/block lists
        if allowed and tool_name not in allowed:
            obs = {"ok": False, "error": f"tool_not_allowed_here: {tool_name}", "allowed": sorted(allowed)}
            messages = llm.observe(messages, tool_name, args, obs)
            steps.append({"tool": tool_name, "args": args, "obs": obs})
            continue
        if tool_name in blocked:
            obs = {"ok": False, "error": f"tool_blocked_by_request: {tool_name}"}
            messages = llm.observe(messages, tool_name, args, obs)
            steps.append({"tool": tool_name, "args": args, "obs": obs})
            continue

        # Example terminal guard
        if tool_name in {"terminal_run", "shell.run"} and isinstance(args.get("cmd"), str):
            try:
                policy_ok, reason = policy.is_exec_allowed("powershell", [args["cmd"]])
                if not policy_ok:
                    raise PermissionError(reason)
            except Exception as e:
                obs = {"ok": False, "error": f"policy_blocked: {e}"}
                messages = llm.observe(messages, tool_name, args, obs)
                steps.append({"tool": tool_name, "args": args, "obs": obs})
                continue

        # Dispatch to tool (supports async callables)
        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
        else:
            try:
                if asyncio.iscoroutinefunction(tool):
                    obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                else:
                    loop = asyncio.get_event_loop()
                    obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)), timeout=per_tool_runtime_sec)
            except asyncio.TimeoutError:
                obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
            except Exception as e:
                logger.exception(f"tool {tool_name} failed")
                obs = {"ok": False, "error": f"tool_error: {e}"}

        # Feed observation back to LLM and record
        try:
            messages = llm.observe(messages, tool_name, args, obs)
        except Exception as e:
            logger.exception("LLM observe failed")
            return {"ok": False, "error": f"llm_observe_failed: {e}"}

        steps.append({"tool": tool_name, "args": args, "obs": obs})

        # Agent-provided stop hint
        if obs.get("ok") and obs.get("stop"):
            logger.info("Received stop signal from tool observation.")
            break

    return {
        "ok": True,
        "goal": goal,  # normalized natural text
        "dry_run": dry_run,
        "options": options,
        "steps": steps,
        "used_max_steps": len(steps),
        "limits": {"max_steps": max_steps, "per_tool_runtime_sec": per_tool_runtime_sec},
    }


# ------------------------- Diagnostics (optional) ------------------------
test_router = FastAPI().router  # lightweight APIRouter
@test_router.get("/debug/playwright")
async def debug_playwright():
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://example.com")
            title = await page.title()
            await browser.close()
        return {"ok": True, "title": title}
    except Exception as e:
        return {"ok": False, "error": str(e)}

app.include_router(test_router)


