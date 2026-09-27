"""Realm schema generation and validation of the emitted JSON Schema subset.

This is deliberately not a general-purpose JSON Schema implementation. The
validator supports every keyword emitted here; schema export uses Draft 2020-12.
"""
from copy import deepcopy
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from functools import lru_cache
import math
from typing import get_args, get_origin, get_type_hints


@lru_cache(maxsize=1)
def _schema_for(manifest_type):
    definitions = {}

    def describe(annotation):
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return {"type": "string", "enum": [item.value for item in annotation]}
        primitive = {str: "string", int: "integer", float: "number", bool: "boolean"}
        if annotation in primitive:
            return {"type": primitive[annotation]}
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is list:
            return {"type": "array", "items": describe(args[0])}
        if origin is dict and args[0] is str:
            return {"type": "object", "additionalProperties": describe(args[1])}
        if is_dataclass(annotation):
            name = annotation.__name__
            if name not in definitions:
                definitions[name] = {}
                hints = get_type_hints(annotation)
                properties = {f.name: describe(hints[f.name]) for f in fields(annotation)}
                required = [f.name for f in fields(annotation)
                            if f.default is MISSING and f.default_factory is MISSING]
                definitions[name] = {
                    "type": "object", "properties": properties,
                    "required": required, "additionalProperties": False,
                }
            return {"$ref": f"#/$defs/{name}"}
        raise TypeError(f"Unsupported manifest annotation: {annotation!r}")

    root = describe(manifest_type)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Play Anything Realm Manifest",
        **root, "$defs": definitions,
    }


def manifest_json_schema(manifest_type):
    """Return an independent, JSON-serializable schema for the manifest."""
    return deepcopy(_schema_for(manifest_type))


def validate_manifest_data(data, manifest_type):
    """Return structural errors with JSON paths; business rules live in Studio."""
    schema = _schema_for(manifest_type)
    errors = []

    def check(value, rule, path):
        if "$ref" in rule:
            rule = schema["$defs"][rule["$ref"].rsplit("/", 1)[1]]
        kind = rule["type"]
        valid = {
            "object": lambda: isinstance(value, dict),
            "array": lambda: isinstance(value, list),
            "string": lambda: isinstance(value, str),
            "boolean": lambda: type(value) is bool,
            "integer": lambda: type(value) is int or (type(value) is float and
                       math.isfinite(value) and value.is_integer()),
            "number": lambda: type(value) in (int, float) and
                      (type(value) is int or math.isfinite(value)),
        }[kind]()
        if not valid:
            errors.append(f"{path}: expected {kind}")
            return
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{path}: invalid enum value {value!r}")
        if kind == "object":
            properties = rule.get("properties", {})
            for key in rule.get("required", []):
                if key not in value:
                    errors.append(f"{path}.{key}: required field missing")
            additional = rule.get("additionalProperties", False)
            for key, child in value.items():
                if not isinstance(key, str):
                    errors.append(f"{path}: object keys must be strings")
                elif key in properties:
                    check(child, properties[key], f"{path}.{key}")
                elif additional is False:
                    errors.append(f"{path}.{key}: unknown field")
                else:
                    check(child, additional, f"{path}.{key}")
        elif kind == "array":
            for index, child in enumerate(value):
                check(child, rule["items"], f"{path}[{index}]")

    check(data, schema, "$")
    return errors
