# --- ADD/KEEP THESE IMPORTS AT TOP OF main.py ---
from __future__ import annotations
import logging
import sys
import asyncio

# ✅ Windows + Playwright + asyncio compatibility
if sys.platform == "win32":
    # Playwright requires subprocess support → use Proactor (default on py3.8+)
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
import time, json, re, shlex, os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger

from typing import AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from loguru import logger
from pathlib import Path

from .tools.registry import TOOL_REGISTRY, get_tool
from .policy import policy
from .llm import LLM

# If you saved TracedLLM as apps/orchestrator/llm_traced.py:
from .llm_traced import TracedLLM
from functools import lru_cache

app = FastAPI()

logger = logging.getLogger("uvicorn.error")  # prints into uvicorn console

@app.on_event("startup")
async def startup_event():
    from . import llm
    client = get_llm()
    if client:
        logger.info(f"✅ LLM initialized at startup with model {os.getenv('OPENAI_MODEL', 'gpt-4o-mini')}")
    else:
        logger.error("❌ LLM not initialized (missing OPENAI_API_KEY?)")

# ---------- UI (optional) ----------
@app.get("/ui", response_class=HTMLResponse)
def ui():
    html_path = Path(__file__).with_name("ui.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))

# ---------- LLM DI ----------
@lru_cache
def get_llm():
    base = LLM()
    return TracedLLM(base)   # always wrap so dump_trace() exists

# ---------- Request model ----------
class TaskRequest(BaseModel):
    goal: str
    dry_run: bool = False
    options: dict | None = None
    budget_rupees: int | None = None

# ---------- Inline-plan fallback parser ----------
def _kv_line_to_args(s: str) -> dict:
    out = {}
    for part in shlex.split(s):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v
    return out

def _extract_option_from_goal(text: str, key: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text, flags=re.I | re.M)
    return m.group(1).strip() if m else None

def _parse_inline_plan_text(goal_text: str) -> list[dict]:
    calls: list[dict] = []
    lines = goal_text.splitlines()
    profile_hint = _extract_option_from_goal(goal_text, "profile")
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(?:-\s*)?([A-Za-z0-9_.]+)\s*:\s*(.+)$", line)
        if not m:
            continue
        tool, rest = m.group(1).strip(), m.group(2).strip()
        args: dict = {}
        if tool == "terminal.run":
            args = {"cmd": rest, "shell": "powershell", "timeout_sec": 300}
        elif tool in {"vscode.open"}:
            args = {"path": rest}
        elif tool in {"vscode.install_extension"}:
            args = {"ext_id": rest}
        elif tool in {"fs.write","fs.move","fs.copy","fs.delete"}:
            args = _kv_line_to_args(rest)
        elif tool in {"fs.listdir"}:
            args = {"path": rest}
        elif tool in {"pkg.install","pkg.uninstall","pkg.ensure"}:
            args = _kv_line_to_args(rest)
        elif tool == "http.request":
            if rest.lower().startswith(("get ","post ","put ","delete ")):
                parts = rest.split(None, 1)
                method = parts[0].upper()
                url = parts[1] if len(parts) > 1 else ""
                args = {"method": method, "url": url}
            else:
                args = _kv_line_to_args(rest)
        elif tool == "browser.execute":
            args = {}
            if rest[:1] in "[{":
                try:
                    args = json.loads(rest)
                except Exception:
                    args = {}
            if profile_hint and "profile" not in args:
                args["profile"] = profile_hint
        else:
            continue
        calls.append({"name": tool, "arguments": args})
    return calls

# ---------- Helpers ----------
def _sse(data: dict) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")

# ---------- Batch endpoint (existing /tasks/run) ----------
@app.post("/tasks/run")
async def run_task(req: TaskRequest, llm: TracedLLM = Depends(get_llm)):
    print("=== ENTERING run_task ===")
    defaults = policy.defaults() or {}
    max_steps = int((req.options or {}).get("max_steps", defaults.get("max_total_steps", 40)))
    per_tool_runtime_sec = int(defaults.get("max_tool_runtime_sec", 120))
    overall_time_budget = max_steps * per_tool_runtime_sec

    print("Hello from main function")

    start_ts = time.time()
    steps: list[dict] = []
    traces: list[str] = []

    # Bootstrap conversation
    try:
        messages = llm.bootstrap(req.goal, req.dry_run, req.budget_rupees)
        print("LLM bootstrap successful")
    except Exception as e:
        print(f"LLM bootstrap failed: {e}")
        logger.exception("LLM bootstrap failed")
        return {"ok": False, "error": f"llm_bootstrap_failed: {e}"}

    for i in range(max_steps):
        if time.time() - start_ts > overall_time_budget:
            print("Time budget exceeded; stopping.")
            logger.warning("Time budget exceeded; stopping.")
            break

        try:
            call = llm.next_tool_call(messages)
            print(f"LLM next_tool_call result: {call}")
        except Exception as e:
            print(f"LLM next_tool_call failed: {e}")
            logger.exception("LLM next_tool_call failed")
            return {"ok": False, "error": f"llm_next_tool_call_failed: {e}"}

        if not call:
            # Inline plan fallback on first iteration
            if i == 0:
                inline_calls = _parse_inline_plan_text(req.goal or "")
                if inline_calls:
                    print(f"Planner empty; executing {len(inline_calls)} inline step(s).")
                    logger.info(f"Planner empty; executing {len(inline_calls)} inline step(s).")
                    for micro in inline_calls:
                        tool_name = micro["name"]
                        args = dict(micro.get("arguments") or {})
                        print(f"Executing inline tool: {tool_name} with args: {args}")
                        if tool_name == "browser.execute":
                            prof = (req.options or {}).get("profile")
                            if prof and "profile" not in args:
                                args["profile"] = prof
                        tool, matched_name = get_tool(tool_name, TOOL_REGISTRY)
                        if not tool:
                            print(f"Tool not found: {tool_name}")
                            obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
                        else:
                            print(f"Tool found: {matched_name}")
                            try:
                                if asyncio.iscoroutinefunction(tool):
                                    obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                                else:
                                    loop = asyncio.get_event_loop()
                                    obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                                 timeout=per_tool_runtime_sec)
                                print(f"Tool {matched_name} result: {obs}")
                            except asyncio.TimeoutError:
                                print(f"Tool {matched_name} timed out")
                                obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                            except Exception as e:
                                print(f"Tool {matched_name} failed: {e}")
                                logger.exception(f"tool {tool_name} failed (inline)")
                                obs = {"ok": False, "error": f"tool_error: {e}"}
                        try:
                            messages = llm.observe(messages, tool_name, args, obs)
                        except Exception:
                            pass
                        steps.append({"tool": tool_name, "args": args, "obs": obs})
                        if obs.get("ok") and obs.get("stop"):
                            break
                    break
            print("No tool call returned, ending.")
            logger.info("No tool call returned, ending.")
            break

        tool_name = call.get("name")
        args = call.get("arguments", {}) or {}
        print(f"[step {i+1}/{max_steps}] {tool_name}({args})")
        logger.info(f"[step {i+1}/{max_steps}] {tool_name}({args})")

        # Dispatch
        if tool_name == "multi_tool_use.parallel":
            print("Handling multi_tool_use.parallel")
            # Expand and run tools sequentially
            obs_results = []
            tool_uses = (args or {}).get("tool_uses") or []
            for micro in tool_uses:
                rname = micro.get("recipient_name") or ""
                params = dict(micro.get("parameters") or {})
                # strip any namespace like "functions."
                short = rname.split(".")[-1]
                print(f"Looking up tool: {short}")
                tool, matched_name = get_tool(short, TOOL_REGISTRY)
                if not tool:
                    print(f"Tool not found: {short}")
                    micro_obs = {"ok": False, "error": f"unknown_tool: {rname}"}
                else:
                    print(f"Tool found: {matched_name}")
                    try:
                        if asyncio.iscoroutinefunction(tool):
                            micro_obs = await asyncio.wait_for(tool(**params), timeout=per_tool_runtime_sec)
                        else:
                            loop = asyncio.get_event_loop()
                            micro_obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**params)),
                                                               timeout=per_tool_runtime_sec)
                        print(f"Tool {matched_name} result: {micro_obs}")
                    except asyncio.TimeoutError:
                        print(f"Tool {matched_name} timed out")
                        micro_obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                    except Exception as e:
                        print(f"Tool {matched_name} failed: {e}")
                        logger.exception(f"tool {rname} failed")
                        micro_obs = {"ok": False, "error": f"tool_error: {e}"}
                obs_results.append({"tool": rname, "args": params, "obs": micro_obs})
            # Respond once to the original parallel call to satisfy tool_call contract
            obs = {"ok": True, "parallel": True, "results": obs_results}
        else:
            print(f"Looking up tool: {tool_name}")
            tool, matched_name = get_tool(tool_name, TOOL_REGISTRY)
            if not tool:
                print(f"Tool not found: {tool_name}")
                obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
            else:
                print(f"Tool found: {matched_name}")
                try:
                    if asyncio.iscoroutinefunction(tool):
                        obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                    else:
                        loop = asyncio.get_event_loop()
                        obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                     timeout=per_tool_runtime_sec)
                    print(f"Tool {matched_name} result: {obs}")
                except asyncio.TimeoutError:
                    print(f"Tool {matched_name} timed out")
                    obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                except Exception as e:
                    print(f"Tool {matched_name} failed: {e}")
                    logger.exception(f"tool {tool_name} failed")
                    obs = {"ok": False, "error": f"tool_error: {e}"}

        try:
            messages = llm.observe(messages, tool_name, args, obs)
            print("LLM observe successful")
        except Exception as e:
            print(f"LLM observe failed: {e}")
            logger.exception("LLM observe failed")
            return {"ok": False, "error": f"llm_observe_failed: {e}"}

        steps.append({"tool": tool_name, "args": args, "obs": obs})
        if obs.get("ok") and obs.get("stop"):
            print("Received stop signal from tool observation.")
            logger.info("Received stop signal from tool observation.")
            break

    print("=== EXITING run_task ===")
    return {
        "ok": True,
        "goal": req.goal,
        "dry_run": req.dry_run,
        "steps": steps,
        "used_max_steps": len(steps),
        "limits": {"max_steps": max_steps, "per_tool_runtime_sec": per_tool_runtime_sec},
        "llm_trace_tail": getattr(llm, "dump_trace", lambda: [])()[-3:],  # helpful on planner silence
        "traces": traces,
    }

# ---------- Streaming endpoint (live trace to UI) ----------
@app.post("/tasks/run_stream")
async def run_task_stream(req: TaskRequest, llm: TracedLLM = Depends(get_llm)):
    print("=== ENTERING run_task_stream ===")
    defaults = policy.defaults() or {}
    max_steps = int((req.options or {}).get("max_steps", defaults.get("max_total_steps", 40)))
    per_tool_runtime_sec = int(defaults.get("max_tool_runtime_sec", 120))
    overall_time_budget = max_steps * per_tool_runtime_sec

    async def gen() -> AsyncGenerator[bytes, None]:
        print("=== ENTERING run_task_stream generator ===")
        start_ts = time.time()
        steps: list[dict] = []
        traces: list[str] = []
        yield _sse({"evt":"agent.start","goal":req.goal,"dry_run":req.dry_run,"options":req.options})

        # Bootstrap
        try:
            messages = llm.bootstrap(req.goal, req.dry_run, req.budget_rupees)
            print("LLM bootstrap successful (stream)")
            tail = llm.dump_trace()[-1] if llm.dump_trace() else None
            yield _sse({"evt":"llm.bootstrap","tail": tail})
        except Exception as e:
            print(f"LLM bootstrap failed (stream): {e}")
            yield _sse({"evt":"error","where":"bootstrap","error":str(e)})
            yield _sse({"evt":"agent.end","ok":False})
            return

        for i in range(max_steps):
            if time.time() - start_ts > overall_time_budget:
                print("Time budget exceeded (stream); stopping.")
                yield _sse({"evt":"agent.timeout","after_sec": overall_time_budget})
                break

            try:
                call = llm.next_tool_call(messages)
                print(f"LLM next_tool_call result (stream): {call}")
                yield _sse({"evt":"llm.next","step":i+1,"call":call})
            except Exception as e:
                print(f"LLM next_tool_call failed (stream): {e}")
                yield _sse({"evt":"error","where":"next_tool_call","error":str(e)})
                break

            if not call:
                # Inline plan fallback (first loop)
                if i == 0:
                    inline_calls = _parse_inline_plan_text(req.goal or "")
                    if inline_calls:
                        print(f"Planner empty; executing {len(inline_calls)} inline step(s) (stream).")
                        yield _sse({"evt":"planner.fallback","count":len(inline_calls)})
                        for micro in inline_calls:
                            tool_name = micro["name"]
                            args = dict(micro.get("arguments") or {})
                            print(f"Executing inline tool (stream): {tool_name} with args: {args}")
                            if tool_name == "browser.execute":
                                prof = (req.options or {}).get("profile")
                                if prof and "profile" not in args:
                                    args["profile"] = prof
                            yield _sse({"evt":"tool.dispatch","step":i+1,"tool":tool_name,"args":args})
                            tool, matched_name = get_tool(tool_name, TOOL_REGISTRY)
                            if not tool:
                                print(f"Tool not found (stream): {tool_name}")
                                obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
                            else:
                                print(f"Tool found (stream): {matched_name}")
                                try:
                                    if asyncio.iscoroutinefunction(tool):
                                        obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                                    else:
                                        loop = asyncio.get_event_loop()
                                        obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                                     timeout=per_tool_runtime_sec)
                                    print(f"Tool {matched_name} result (stream): {obs}")
                                except asyncio.TimeoutError:
                                    print(f"Tool {matched_name} timed out (stream)")
                                    obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                                except Exception as e:
                                    print(f"Tool {matched_name} failed (stream): {e}")
                                    obs = {"ok": False, "error": f"tool_error: {e}"}
                            yield _sse({"evt":"tool.obs","step":i+1,"tool":tool_name,"obs":obs})
                            steps.append({"tool": tool_name, "args": args, "obs": obs})
                            try:
                                messages = llm.observe(messages, tool_name, args, obs)
                                print("LLM observe successful (stream)")
                                yield _sse({"evt":"llm.observe","step":i+1})
                            except Exception:
                                print("LLM observe failed (stream)")
                                pass
                            if obs.get("ok") and obs.get("stop"):
                                print("Received stop signal (stream)")
                                yield _sse({"evt":"agent.stop_signal"})
                                break
                        break
                print("No tool call returned (stream), ending.")
                yield _sse({"evt":"llm.silent","last": (llm.dump_trace()[-1] if llm.dump_trace() else None)})
                break

            tool_name = call.get("name")
            args = call.get("arguments", {}) or {}
            print(f"[step {i+1}/{max_steps}] {tool_name}({args}) (stream)")
            yield _sse({"evt":"tool.dispatch","step":i+1,"tool":tool_name,"args":args})

            if tool_name == "multi_tool_use.parallel":
                print("Handling multi_tool_use.parallel (stream)")
                obs_results = []
                tool_uses = (args or {}).get("tool_uses") or []
                for micro in tool_uses:
                    rname = micro.get("recipient_name") or ""
                    params = dict(micro.get("parameters") or {})
                    short = rname.split(".")[-1]
                    print(f"Looking up tool (stream): {short}")
                    yield _sse({"evt":"tool.dispatch","step":i+1,"tool":short,"args":params})
                    tool, matched_name = get_tool(short, TOOL_REGISTRY)
                    if not tool:
                        print(f"Tool not found (stream): {short}")
                        micro_obs = {"ok": False, "error": f"unknown_tool: {rname}"}
                    else:
                        print(f"Tool found (stream): {matched_name}")
                        try:
                            if asyncio.iscoroutinefunction(tool):
                                micro_obs = await asyncio.wait_for(tool(**params), timeout=per_tool_runtime_sec)
                            else:
                                loop = asyncio.get_event_loop()
                                micro_obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**params)),
                                                                   timeout=per_tool_runtime_sec)
                            print(f"Tool {matched_name} result (stream): {micro_obs}")
                        except asyncio.TimeoutError:
                            print(f"Tool {matched_name} timed out (stream)")
                            micro_obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                        except Exception as e:
                            print(f"Tool {matched_name} failed (stream): {e}")
                            micro_obs = {"ok": False, "error": f"tool_error: {e}"}
                    obs_results.append({"tool": rname, "args": params, "obs": micro_obs})
                    yield _sse({"evt":"tool.obs","step":i+1,"tool":short,"obs":micro_obs})
                    steps.append({"tool": short, "args": params, "obs": micro_obs})
                # Respond once to the original parallel call
                obs = {"ok": True, "parallel": True, "results": obs_results}
            else:
                print(f"Looking up tool (stream): {tool_name}")
                tool, matched_name = get_tool(tool_name, TOOL_REGISTRY)
                if not tool:
                    print(f"Tool not found (stream): {tool_name}")
                    obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
                else:
                    print(f"Tool found (stream): {matched_name}")
                    try:
                        if asyncio.iscoroutinefunction(tool):
                            obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                        else:
                            loop = asyncio.get_event_loop()
                            obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                         timeout=per_tool_runtime_sec)
                        print(f"Tool {matched_name} result (stream): {obs}")
                    except asyncio.TimeoutError:
                        print(f"Tool {matched_name} timed out (stream)")
                        obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                    except Exception as e:
                        print(f"Tool {matched_name} failed (stream): {e}")
                        obs = {"ok": False, "error": f"tool_error: {e}"}

            yield _sse({"evt":"tool.obs","step":i+1,"tool":tool_name,"obs":obs})
            steps.append({"tool": tool_name, "args": args, "obs": obs})

            try:
                messages = llm.observe(messages, tool_name, args, obs)
                print("LLM observe successful (stream)")
                yield _sse({"evt":"llm.observe","step":i+1})
            except Exception as e:
                print(f"LLM observe failed (stream): {e}")
                yield _sse({"evt":"error","where":"observe","error":str(e)})
                break

            if obs.get("ok") and obs.get("stop"):
                print("Received stop signal (stream)")
                yield _sse({"evt":"agent.stop_signal"})
                break

        print("=== EXITING run_task_stream generator ===")
        yield _sse({"evt":"agent.end","ok": True, "steps": len(steps)})

    return StreamingResponse(gen(), media_type="text/event-stream")
