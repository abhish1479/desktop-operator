from pathlib import Path
import yaml

def load_manifest(tool: str) -> dict:
    p = Path(f"skills/{tool}/manifest.yaml")
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8"))
