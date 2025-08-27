# --- ADD/KEEP THESE IMPORTS AT TOP OF main.py ---
from __future__ import annotations
import asyncio, time, json, re, shlex
from typing import AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from loguru import logger
from pathlib import Path

from .tools.registry import TOOL_REGISTRY
from .policy import policy
from .llm import LLM

# If you saved TracedLLM as apps/orchestrator/llm_traced.py:
from .llm_traced import TracedLLM
from functools import lru_cache

app = FastAPI()

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
    defaults = policy.defaults() or {}
    max_steps = int((req.options or {}).get("max_steps", defaults.get("max_total_steps", 40)))
    per_tool_runtime_sec = int(defaults.get("max_tool_runtime_sec", 120))
    overall_time_budget = max_steps * per_tool_runtime_sec

    start_ts = time.time()
    steps: list[dict] = []

    # Bootstrap conversation
    try:
        messages = llm.bootstrap(req.goal, req.dry_run, req.budget_rupees)
    except Exception as e:
        logger.exception("LLM bootstrap failed")
        return {"ok": False, "error": f"llm_bootstrap_failed: {e}"}

    for i in range(max_steps):
        if time.time() - start_ts > overall_time_budget:
            logger.warning("Time budget exceeded; stopping.")
            break

        try:
            call = llm.next_tool_call(messages)
        except Exception as e:
            logger.exception("LLM next_tool_call failed")
            return {"ok": False, "error": f"llm_next_tool_call_failed: {e}"}

        if not call:
            # Inline plan fallback on first iteration
            if i == 0:
                inline_calls = _parse_inline_plan_text(req.goal or "")
                if inline_calls:
                    logger.info(f"Planner empty; executing {len(inline_calls)} inline step(s).")
                    for micro in inline_calls:
                        tool_name = micro["name"]
                        args = dict(micro.get("arguments") or {})
                        if tool_name == "browser.execute":
                            prof = (req.options or {}).get("profile")
                            if prof and "profile" not in args:
                                args["profile"] = prof
                        tool = TOOL_REGISTRY.get(tool_name)
                        if not tool:
                            obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
                        else:
                            try:
                                if asyncio.iscoroutinefunction(tool):
                                    obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                                else:
                                    loop = asyncio.get_event_loop()
                                    obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                                 timeout=per_tool_runtime_sec)
                            except asyncio.TimeoutError:
                                obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                            except Exception as e:
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
            logger.info("No tool call returned, ending.")
            break

        tool_name = call.get("name")
        args = call.get("arguments", {}) or {}
        logger.info(f"[step {i+1}/{max_steps}] {tool_name}({args})")

        # Dispatch
        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
        else:
            try:
                if asyncio.iscoroutinefunction(tool):
                    obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                else:
                    loop = asyncio.get_event_loop()
                    obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                 timeout=per_tool_runtime_sec)
            except asyncio.TimeoutError:
                obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
            except Exception as e:
                logger.exception(f"tool {tool_name} failed")
                obs = {"ok": False, "error": f"tool_error: {e}"}

        try:
            messages = llm.observe(messages, tool_name, args, obs)
        except Exception as e:
            logger.exception("LLM observe failed")
            return {"ok": False, "error": f"llm_observe_failed: {e}"}

        steps.append({"tool": tool_name, "args": args, "obs": obs})
        if obs.get("ok") and obs.get("stop"):
            logger.info("Received stop signal from tool observation.")
            break

    return {
        "ok": True,
        "goal": req.goal,
        "dry_run": req.dry_run,
        "steps": steps,
        "used_max_steps": len(steps),
        "limits": {"max_steps": max_steps, "per_tool_runtime_sec": per_tool_runtime_sec},
        "llm_trace_tail": getattr(llm, "dump_trace", lambda: [])()[-3:],  # helpful on planner silence
    }

# ---------- Streaming endpoint (live trace to UI) ----------
@app.post("/tasks/run_stream")
async def run_task_stream(req: TaskRequest, llm: TracedLLM = Depends(get_llm)):
    defaults = policy.defaults() or {}
    max_steps = int((req.options or {}).get("max_steps", defaults.get("max_total_steps", 40)))
    per_tool_runtime_sec = int(defaults.get("max_tool_runtime_sec", 120))
    overall_time_budget = max_steps * per_tool_runtime_sec

    async def gen() -> AsyncGenerator[bytes, None]:
        start_ts = time.time()
        steps: list[dict] = []
        yield _sse({"evt":"agent.start","goal":req.goal,"dry_run":req.dry_run,"options":req.options})

        # Bootstrap
        try:
            messages = llm.bootstrap(req.goal, req.dry_run, req.budget_rupees)
            tail = llm.dump_trace()[-1] if llm.dump_trace() else None
            yield _sse({"evt":"llm.bootstrap","tail": tail})
        except Exception as e:
            yield _sse({"evt":"error","where":"bootstrap","error":str(e)})
            yield _sse({"evt":"agent.end","ok":False})
            return

        for i in range(max_steps):
            if time.time() - start_ts > overall_time_budget:
                yield _sse({"evt":"agent.timeout","after_sec": overall_time_budget})
                break

            try:
                call = llm.next_tool_call(messages)
                yield _sse({"evt":"llm.next","step":i+1,"call":call})
            except Exception as e:
                yield _sse({"evt":"error","where":"next_tool_call","error":str(e)})
                break

            if not call:
                # Inline plan fallback (first loop)
                if i == 0:
                    inline_calls = _parse_inline_plan_text(req.goal or "")
                    if inline_calls:
                        yield _sse({"evt":"planner.fallback","count":len(inline_calls)})
                        for micro in inline_calls:
                            tool_name = micro["name"]
                            args = dict(micro.get("arguments") or {})
                            if tool_name == "browser.execute":
                                prof = (req.options or {}).get("profile")
                                if prof and "profile" not in args:
                                    args["profile"] = prof
                            yield _sse({"evt":"tool.dispatch","step":i+1,"tool":tool_name,"args":args})
                            tool = TOOL_REGISTRY.get(tool_name)
                            if not tool:
                                obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
                            else:
                                try:
                                    if asyncio.iscoroutinefunction(tool):
                                        obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                                    else:
                                        loop = asyncio.get_event_loop()
                                        obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                                     timeout=per_tool_runtime_sec)
                                except asyncio.TimeoutError:
                                    obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                                except Exception as e:
                                    obs = {"ok": False, "error": f"tool_error: {e}"}
                            yield _sse({"evt":"tool.obs","step":i+1,"tool":tool_name,"obs":obs})
                            steps.append({"tool": tool_name, "args": args, "obs": obs})
                            try:
                                messages = llm.observe(messages, tool_name, args, obs)
                                yield _sse({"evt":"llm.observe","step":i+1})
                            except Exception:
                                pass
                            if obs.get("ok") and obs.get("stop"):
                                yield _sse({"evt":"agent.stop_signal"})
                                break
                        break
                yield _sse({"evt":"llm.silent","last": (llm.dump_trace()[-1] if llm.dump_trace() else None)})
                break

            tool_name = call.get("name")
            args = call.get("arguments", {}) or {}
            yield _sse({"evt":"tool.dispatch","step":i+1,"tool":tool_name,"args":args})

            tool = TOOL_REGISTRY.get(tool_name)
            if not tool:
                obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
            else:
                try:
                    if asyncio.iscoroutinefunction(tool):
                        obs = await asyncio.wait_for(tool(**args), timeout=per_tool_runtime_sec)
                    else:
                        loop = asyncio.get_event_loop()
                        obs = await asyncio.wait_for(loop.run_in_executor(None, lambda: tool(**args)),
                                                     timeout=per_tool_runtime_sec)
                except asyncio.TimeoutError:
                    obs = {"ok": False, "error": f"tool_timeout_{per_tool_runtime_sec}s"}
                except Exception as e:
                    obs = {"ok": False, "error": f"tool_error: {e}"}

            yield _sse({"evt":"tool.obs","step":i+1,"tool":tool_name,"obs":obs})
            steps.append({"tool": tool_name, "args": args, "obs": obs})

            try:
                messages = llm.observe(messages, tool_name, args, obs)
                yield _sse({"evt":"llm.observe","step":i+1})
            except Exception as e:
                yield _sse({"evt":"error","where":"observe","error":str(e)})
                break

            if obs.get("ok") and obs.get("stop"):
                yield _sse({"evt":"agent.stop_signal"})
                break

        yield _sse({"evt":"agent.end","ok": True, "steps": len(steps)})

    return StreamingResponse(gen(), media_type="text/event-stream")
