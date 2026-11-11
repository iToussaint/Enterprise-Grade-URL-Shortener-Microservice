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


def register_schema(ns: Namespace, model: type[BaseModel]) -> Any:
    """Register a Pydantic model's JSON Schema as a Swagger definition.

    Swagger shows the schema Pydantic generates, so the documented schema and the
    validation rules come from the same model. Nested models are inlined because
    Flask-RESTX only publishes models that are referenced directly; it does not
    follow "$ref"s inside a raw JSON Schema.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return ns.schema_model(model.__name__, inline_references(schema, definitions))
