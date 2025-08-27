# apps/worker/fs.py
from __future__ import annotations
import os, shutil, glob, time
from typing import Dict, Any, List

def _ts(): return int(time.time())

def fs_read(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
    with open(path, "r", encoding=encoding) as f:
        return {"ok": True, "path": path, "content": f.read()}

def fs_write(path: str, content: str, append: bool = False, encoding: str = "utf-8") -> Dict[str, Any]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    mode = "a" if append else "w"
    with open(path, mode, encoding=encoding) as f:
        f.write(content)
    return {"ok": True, "path": path, "bytes": len(content)}

def fs_move(src: str, dst: str, overwrite: bool = True) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if overwrite and os.path.exists(dst):
        if os.path.isdir(dst): shutil.rmtree(dst)
        else: os.remove(dst)
    shutil.move(src, dst)
    return {"ok": True, "src": src, "dst": dst}

def fs_copy(src: str, dst: str, overwrite: bool = True) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if os.path.isdir(src):
        if overwrite and os.path.exists(dst): shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        if overwrite and os.path.exists(dst): os.remove(dst)
        shutil.copy2(src, dst)
    return {"ok": True, "src": src, "dst": dst}

def fs_delete(path: str, recursive: bool = False, dry_run: bool = True) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": True, "deleted": 0, "dry_run": dry_run}
    deleted = 0
    if dry_run:
        if os.path.isdir(path):
            for _root, dirs, files in os.walk(path):
                deleted += len(dirs) + len(files)
        else:
            deleted = 1
        return {"ok": True, "deleted": deleted, "dry_run": True}
    if os.path.isdir(path):
        if not recursive:
            return {"ok": False, "error": "dir_not_empty_without_recursive"}
        shutil.rmtree(path); deleted = 1
    else:
        os.remove(path); deleted = 1
    return {"ok": True, "deleted": deleted, "dry_run": False}

def fs_listdir(path: str, pattern: str | None = None, recursive: bool = False) -> Dict[str, Any]:
    if pattern:
        matches = glob.glob(os.path.join(path, "**", pattern) if recursive else os.path.join(path, pattern),
                            recursive=recursive)
        return {"ok": True, "path": path, "pattern": pattern, "entries": matches}
    return {"ok": True, "path": path, "entries": [os.path.join(path, p) for p in os.listdir(path)]}
