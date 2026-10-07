"""Realm schema generation and validation of the emitted JSON Schema subset.

This is deliberately not a general-purpose JSON Schema implementation. The
validator supports every keyword emitted here; schema export uses Draft 2020-12.
"""
from copy import deepcopy
from dataclasses import MISSING, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from functools import lru_cache
import math
import sys
from typing import get_args, get_origin, get_type_hints


class _ParsedJSONFloat(float):
    """A regular float that retains the source token for exact integer checks."""

    def __new__(cls, token):
        value = float(token)
        parsed = super().__new__(cls, value)
        parsed.token = token
        return parsed


def _compare_json_number_token(token, bound):
    """Compare a finite parsed JSON float token exactly to a schema bound.

    Decimal rejects exponents beyond its implementation range. The JSON
    parser has already produced a finite float before this helper is used, so
    an out-of-range exponent can only leave a zero-valued token or a nonzero
    value underflowed to signed zero. Compare those values by sign and zero
    significand without converting the exponent to an unbounded Python int.
    """
    try:
        exact = Decimal(token)
    except InvalidOperation:
        significand = token.lower().split("e", 1)[0].lstrip("+-")
        if not any(character in "123456789" for character in significand):
            return 0
        if bound == 0:
            return -1 if token.startswith("-") else 1
        # With an exponent outside Decimal's range and a finite parsed float,
        # the magnitude is below any nonzero finite schema bound.
        return -1 if bound > 0 else 1
    return (exact > bound) - (exact < bound)


def normalize_parsed_json_numbers(value, annotation=None):
    """Remove parser markers after validation, preserving declared numeric types."""
    if type(value) is _ParsedJSONFloat:
        if annotation is int:
            exact = Decimal(value.token)
            if not math.isfinite(value) or exact != Decimal.from_float(float(value)):
                get_digit_limit = getattr(sys, "get_int_max_str_digits", None)
                digit_limit = get_digit_limit() if get_digit_limit is not None else 4300
                if digit_limit == 0:
                    digit_limit = 4300
                if exact != 0 and exact.adjusted() + 1 > digit_limit:
                    raise ValueError(
                        "Invalid manifest JSON: exact integer exceeds the runtime digit limit "
                        f"({digit_limit})"
                    )
                return int(exact)
        return float(value)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if is_dataclass(annotation) and isinstance(value, dict):
        hints = get_type_hints(annotation)
        return {
            key: normalize_parsed_json_numbers(child, hints.get(key))
            for key, child in value.items()
        }
    if origin is list and isinstance(value, list):
        item_type = args[0] if args else None
        return [normalize_parsed_json_numbers(child, item_type) for child in value]
    if origin is dict and isinstance(value, dict):
        value_type = args[1] if len(args) > 1 else None
        return {key: normalize_parsed_json_numbers(child, value_type)
                for key, child in value.items()}
    if isinstance(value, dict):
        return {key: normalize_parsed_json_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_parsed_json_numbers(child) for child in value]
    return value


@lru_cache(maxsize=1)
def _schema_for(manifest_type):
    definitions = {}

    def describe(annotation, metadata=None):
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return {"type": "string", "enum": [item.value for item in annotation]}
        primitive = {str: "string", int: "integer", float: "number", bool: "boolean"}
        if annotation in primitive:
            rule = {"type": primitive[annotation]}
            if annotation in (int, float) and metadata:
                for keyword in ("minimum", "maximum"):
                    if keyword in metadata:
                        rule[keyword] = metadata[keyword]
            return rule
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
                properties = {f.name: describe(hints[f.name], f.metadata)
                              for f in fields(annotation)}
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

    def is_integer(value):
        if type(value) is int:
            return True
        if type(value) is float:
            return math.isfinite(value) and value.is_integer()
        if type(value) is _ParsedJSONFloat:
            try:
                exact = Decimal(value.token)
                return exact.is_finite() and exact == exact.to_integral_value()
            except (InvalidOperation, ValueError):
                return False
        return False

    def check(value, rule, path):
        if "$ref" in rule:
            rule = schema["$defs"][rule["$ref"].rsplit("/", 1)[1]]
        kind = rule["type"]
        valid = {
            "object": lambda: isinstance(value, dict),
            "array": lambda: isinstance(value, list),
            "string": lambda: isinstance(value, str),
            "boolean": lambda: type(value) is bool,
            "integer": lambda: is_integer(value),
            "number": lambda: type(value) in (int, float, _ParsedJSONFloat) and
                      (type(value) is int or math.isfinite(value)),
        }[kind]()
        if not valid:
            errors.append(f"{path}: expected {kind}")
            return
        if kind in ("integer", "number") and type(value) is _ParsedJSONFloat:
            for keyword, operator in (("minimum", "<"), ("maximum", ">")):
                if keyword not in rule:
                    continue
                bound = Decimal(str(rule[keyword]))
                comparison = _compare_json_number_token(value.token, bound)
                outside = comparison < 0 if operator == "<" else comparison > 0
                if outside:
                    relation = "at least" if keyword == "minimum" else "at most"
                    errors.append(f"{path}: must be {relation} {rule[keyword]}")
        elif kind in ("integer", "number"):
            for keyword, operator in (("minimum", "<"), ("maximum", ">")):
                if keyword not in rule:
                    continue
                bound = rule[keyword]
                outside = value < bound if operator == "<" else value > bound
                if outside:
                    relation = "at least" if keyword == "minimum" else "at most"
                    errors.append(f"{path}: must be {relation} {bound}")
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
