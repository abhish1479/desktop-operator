import json
from pathlib import Path
from jsonschema import Draft202012Validator

_validator_cache = {}

def validate_input(tool_name: str, payload: dict):
    schema_path = Path(f"skills/{tool_name}/schema.json")
    if not schema_path.exists():
        return  # no schema -> accept for now
    if tool_name not in _validator_cache:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        _validator_cache[tool_name] = Draft202012Validator(schema)
    v = _validator_cache[tool_name]
    errors = sorted(v.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msgs = [f"{'/'.join([str(p) for p in e.path])}: {e.message}" for e in errors]
        raise ValueError("Schema validation failed: " + "; ".join(msgs))
