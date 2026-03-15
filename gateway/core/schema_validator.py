import json
import os
from functools import lru_cache

import jsonschema
from jsonschema import ValidationError

# Path to the JSON schemas directory
SCHEMAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schemas", "json")


@lru_cache(maxsize=128)
def _load_schema(action: str) -> dict | None:
    """Load and cache a JSON schema for the given OCPP action."""
    schema_path = os.path.join(SCHEMAS_DIR, f"{action}.json")
    if not os.path.exists(schema_path):
        return None
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate(action: str, payload: dict) -> None:
    """
    Validate a payload against the OCPP JSON schema for the given action.
    Raises jsonschema.ValidationError if validation fails.
    Silently passes if no schema exists for the action (unknown action).
    """
    schema = _load_schema(action)
    if schema is None:
        # No schema available; skip validation
        return
    jsonschema.validate(instance=payload, schema=schema)


def has_schema(action: str) -> bool:
    """Check if a schema exists for the given action."""
    return _load_schema(action) is not None
