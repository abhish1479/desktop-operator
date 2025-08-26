from fastapi import FastAPI
from pydantic import BaseModel
from loguru import logger

from .llm import LLM
from .policy import Guardrails
from .tools.registry import TOOL_REGISTRY
from .skills_router import router as skills_router

app = FastAPI(title="Desktop Operator Orchestrator", version="0.1.0")
app.include_router(skills_router, prefix="/skills", tags=["skills"])

llm = LLM()
guard = Guardrails()

class TaskRequest(BaseModel):
    goal: str
    budget_rupees: int | None = None
    dry_run: bool = True

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.post("/tasks/run")
async def run_task(req: TaskRequest):
    messages = llm.bootstrap(req.goal, req.dry_run, req.budget_rupees)
    steps = []

    for i in range(guard.max_steps()):
        call = llm.next_tool_call(messages)
        if not call:
            logger.info("No tool call returned, ending.")
            break

        tool_name = call.get("name")
        args = call.get("arguments", {})
        logger.info(f"Step {i+1}: {tool_name}({args})")

        # Guardrails for terminal calls
        if tool_name == "terminal_run":
            guard.validate_terminal(args.get("cmd",""))

        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            obs = {"ok": False, "error": f"unknown_tool: {tool_name}"}
        else:
            obs = await tool(**args)

        messages = llm.observe(messages, tool_name, args, obs)
        steps.append({"tool": tool_name, "args": args, "obs": obs})

        if obs.get("ok") and obs.get("stop"):
            break

        if guard.time_budget_exceeded():
            break

    return {"ok": True, "steps": steps}
