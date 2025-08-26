from fastapi import APIRouter
from pydantic import BaseModel

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
