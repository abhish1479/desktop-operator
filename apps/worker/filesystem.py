import os, shutil
from pathlib import Path

def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)

def write_text(path: str, content: str) -> dict:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p), "bytes": len(content)}

def move_path(src: str, dst: str) -> dict:
    s = Path(src); d = Path(dst)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return {"ok": True, "src": str(s), "dst": str(d)}

def listdir_path(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "path_not_found", "path": str(p)}
    items = [f.name for f in p.iterdir()]
    return {"ok": True, "items": items, "count": len(items)}
