# apps/worker/filesystem.py - CREATE THIS FILE
from __future__ import annotations
from .fs import fs_write, fs_move, fs_listdir
from typing import Dict, Any

def write_text(path: str, content: str) -> Dict[str, Any]:
    """Wrapper to match registry.py expectations"""
    return fs_write(path, content)

def move_path(src: str, dst: str) -> Dict[str, Any]:
    """Wrapper to match registry.py expectations"""  
    return fs_move(src, dst)

def listdir_path(path: str) -> Dict[str, Any]:
    """Wrapper to match registry.py expectations"""
    return fs_listdir(path)