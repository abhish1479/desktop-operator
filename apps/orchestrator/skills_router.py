from fastapi import APIRouter
from pydantic import BaseModel
from .validation import validate_input
from .policy import policy

from ..worker.filesystem import ensure_dir
from ..worker.skills.files_organize import run as files_organize_run
from ..worker.skills.shopify_bulk import run as shopify_bulk_run

router = APIRouter()

class OrganizeReq(BaseModel):
    root: str
    rules: list[dict]
    dry_run: bool = True

@router.post("/files.organize/run")
async def files_organize(req: OrganizeReq):
    ensure_dir(req.root)
    result = files_organize_run(req.root, req.rules, req.dry_run)
    return result

class ShopifyReq(BaseModel):
    csv_path: str
    update: bool = True

@router.post("/shopify.bulk_upload/run")
async def shopify_bulk(req: ShopifyReq):
    result = shopify_bulk_run(req.csv_path, req.update)
    return result



from pydantic import BaseModel
from ..worker.skills.whatsapp_chat import run_chat

class WhatsappChatReq(BaseModel):
    contact: str
    profile_dir: str
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

@router.post("/{tool}/run")
def run_tool(tool: str, payload: dict):
    # 1) JSON Schema validation
    try:
        validate_input(tool, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 2) Apply defaults from policy
    defaults = policy.defaults()
    for k, v in defaults.items():
        payload.setdefault(k, v)

    # 3) Extra policy checks for known tools
    caps = policy.tool_caps(tool)
    if tool == "files.organize":
        if not payload.get("dry_run", True) and not caps.get("allow_delete", False):
            # If any rule has delete, require approval
            if any(r.get("action") == "delete" for r in payload.get("rules", [])):
                if policy.require_approval("destructive"):
                    raise HTTPException(403, "Delete requires approval")

    # 4) Dispatch (call your existing implementation)
    return _dispatch_tool(tool, payload)
