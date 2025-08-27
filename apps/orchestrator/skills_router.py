# apps/orchestrator/skills_router.py
from __future__ import annotations

import asyncio
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .validation import validate_input
from .policy import policy
from .tools.registry import TOOL_REGISTRY

# Your concrete skill impls
from ..worker.filesystem import ensure_dir
from ..worker.skills.files_organize import run as files_organize_run
from ..worker.skills.shopify_bulk import run as shopify_bulk_run
from ..worker.skills.whatsapp_chat import run_chat

# Prefix so paths are /skills/...
router = APIRouter(prefix="/skills", tags=["skills"])

# -------------------- Explicit skill endpoints --------------------

class OrganizeReq(BaseModel):
    root: str
    rules: list[dict]
    dry_run: bool = True

@router.post("/files.organize/run")
async def files_organize(req: OrganizeReq):
    ensure_dir(req.root)
    return files_organize_run(req.root, req.rules, req.dry_run)

class ShopifyReq(BaseModel):
    csv_path: str
    update: bool = True

@router.post("/shopify.bulk_upload/run")
async def shopify_bulk(req: ShopifyReq):
    return shopify_bulk_run(req.csv_path, req.update)

class WhatsappChatReq(BaseModel):
    contact: str
    profile_dir: str            # e.g. "data/playwright-profiles/default"
    initial_message: str | None = None
    duration_sec: int = 120
    allow_llm: bool = True

@router.post("/whatsapp.chat/run")
async def whatsapp_chat(req: WhatsappChatReq):
    return await run_chat(
        contact=req.contact,
        profile_dir=req.profile_dir,
        initial_message=req.initial_message,
        duration_sec=req.duration_sec,
        allow_llm=req.allow_llm,
    )

# -------------------- Generic dispatcher (for any TOOL_REGISTRY tools) --------------------

async def _dispatch_tool(tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call a tool from TOOL_REGISTRY with a per-tool timeout; works for sync/async."""
    func = TOOL_REGISTRY.get(tool)
    if not func:
        raise HTTPException(404, f"unknown_tool: {tool}")

    timeout = int((policy.defaults() or {}).get("max_tool_runtime_sec", 120))
    try:
        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(func(**payload), timeout=timeout)
        else:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(loop.run_in_executor(None, lambda: func(**payload)), timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(504, f"tool_timeout_{timeout}s")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"tool_error: {e}")

@router.post("/{tool}/run")
async def run_tool(tool: str, payload: Dict[str, Any]):
    # 1) JSON Schema validation (no-op if schema.json doesn’t exist)
    try:
        validate_input(tool, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 2) Apply policy defaults (e.g., dry_run, max steps, etc.)
    for k, v in (policy.defaults() or {}).items():
        payload.setdefault(k, v)

    # 3) Example guard: block deletes unless policy allows
    if tool == "files.organize":
        caps = policy.tool_caps(tool) or {}
        if not caps.get("allow_delete", False) and any(r.get("action") == "delete" for r in payload.get("rules", [])):
            raise HTTPException(403, "delete_not_allowed_by_policy")

    # 4) Dispatch
    return await _dispatch_tool(tool, payload)
