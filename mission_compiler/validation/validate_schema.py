from __future__ import annotations

from jsonschema import Draft202012Validator

from mission_compiler.errors import SchemaValidationError
from mission_compiler.io import read_json, schema_path


def validate_schema(spec: dict) -> list[dict]:
    schema = read_json(schema_path("mission_spec.schema.json"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))
    if errors:
        messages = []
        for err in errors:
            loc = ".".join(str(x) for x in err.path) or "<root>"
            messages.append(f"{loc}: {err.message}")
        raise SchemaValidationError("; ".join(messages))
    return [{"check_id": "schema", "status": "passed", "severity": "error", "message": "MissionSpec matches schema."}]
