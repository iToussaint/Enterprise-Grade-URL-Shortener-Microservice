"""Validate real responses against the schemas published in swagger.json."""

from typing import Any

import jsonschema
from flask.testing import FlaskClient


def nullable_to_json_schema(node: Any) -> Any:
    """Turn Swagger 2.0's "x-nullable": true into JSON Schema's "or null"."""
    if isinstance(node, list):
        return [nullable_to_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: nullable_to_json_schema(value) for key, value in node.items()}
    if node.pop("x-nullable", False):
        return {"anyOf": [node, {"type": "null"}]}
    return node


def assert_matches_schema(client: FlaskClient, definition: str, body: Any) -> None:
    spec = client.get("/api/swagger.json").json
    assert spec is not None
    schema = {
        "$ref": f"#/definitions/{definition}",
        "definitions": nullable_to_json_schema(spec["definitions"]),
    }
    jsonschema.validate(body, schema)
