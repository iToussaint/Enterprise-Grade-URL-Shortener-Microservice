from typing import Any

from flask_restx import Namespace
from pydantic import BaseModel


def inline_references(node: Any, definitions: dict[str, Any]) -> Any:
    """Replace every {"$ref": "#/$defs/Name"} with the definition it points to."""
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return inline_references(definitions[name], definitions)
        return {
            key: inline_references(value, definitions) for key, value in node.items()
        }
    if isinstance(node, list):
        return [inline_references(item, definitions) for item in node]
    return node


def mark_nullable(node: Any) -> Any:
    """Rewrite Pydantic's optional fields for Swagger 2.0.

    `X | None` becomes {"anyOf": [X, {"type": "null"}]}, but Swagger 2.0 has
    neither `anyOf` nor a null type. Its convention is X plus "x-nullable": true.
    """
    if isinstance(node, list):
        return [mark_nullable(item) for item in node]
    if not isinstance(node, dict):
        return node
    options = node.get("anyOf")
    if isinstance(options, list) and len(options) == 2 and {"type": "null"} in options:
        other = next(option for option in options if option != {"type": "null"})
        rest = {key: value for key, value in node.items() if key != "anyOf"}
        node = {**other, **rest, "x-nullable": True}
    return {key: mark_nullable(value) for key, value in node.items()}


def register_schema(ns: Namespace, model: type[BaseModel]) -> Any:
    """Register a Pydantic model's JSON Schema as a Swagger definition.

    Swagger shows the schema Pydantic generates, so the documented schema and the
    validation rules come from the same model. Nested models are inlined because
    Flask-RESTX only publishes models that are referenced directly; it does not
    follow "$ref"s inside a raw JSON Schema. Optional fields are rewritten into
    Swagger 2.0's form (see mark_nullable).
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    schema = mark_nullable(inline_references(schema, definitions))
    return ns.schema_model(model.__name__, schema)
