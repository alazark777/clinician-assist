"""Offline validator for exactly the JSON Schema subset used by this kit.

Not a general JSON Schema engine. Unknown keywords raise instead of silently
passing. Replace with a pinned full validator in the implemented application's CI.
"""
from datetime import date
import json
import re

KNOWN = {"$schema", "title", "description", "type", "properties", "required", "additionalProperties",
         "enum", "const", "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength",
         "minimum", "maximum", "format", "anyOf", "allOf", "if", "then"}


def validate(value, schema, path="$"):
    unknown = set(schema) - KNOWN
    if unknown:
        raise ValueError("Unsupported schema keywords: " + str(unknown))
    errors = []
    kinds = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "integer": type(value) is int,
             "number": type(value) in (int, float), "boolean": type(value) is bool, "null": value is None}
    required_types = schema.get("type", [])
    if isinstance(required_types, str):
        required_types = [required_types]
    if required_types and not any(kinds[t] for t in required_types):
        return [path + ":type"]
    if "const" in schema and value != schema["const"]:
        errors.append(path + ":const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(path + ":enum")
    if "anyOf" in schema and not any(not validate(value, s, path) for s in schema["anyOf"]):
        errors.append(path + ":anyOf")
    for s in schema.get("allOf", []):
        errors.extend(validate(value, s, path))
    if "if" in schema and not validate(value, schema["if"], path):
        errors.extend(validate(value, schema.get("then", {}), path))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(path + ":missing:" + key)
        if schema.get("additionalProperties") is False and set(value) - set(props):
            errors.append(path + ":unknown_fields")
        for key in set(value) & set(props):
            errors.extend(validate(value[key], props[key], path + "." + key))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            errors.append(path + ":array_length")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append(path + ":duplicate_items")
        for i, item in enumerate(value):
            errors.extend(validate(item, schema.get("items", {}), path + f"[{i}]"))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            errors.append(path + ":string_length")
        if schema.get("format") == "date":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError()
                date.fromisoformat(value)
            except ValueError:
                errors.append(path + ":date_format")
    if type(value) in (int, float):
        if value < schema.get("minimum", float("-inf")) or value > schema.get("maximum", float("inf")):
            errors.append(path + ":numeric_range")
    return errors
