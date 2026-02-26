from pydantic import BaseModel, create_model, Field
from typing import List, Optional, Union, get_origin, get_args, Any, Type


# ----------------------------
# Helper: Convert user type string → Python type
# ----------------------------
def python_type_from_user_type(t: str):
    mapping = {
        "string": str,
        "float": float,
        "integer": int,
        "number": float,
        "boolean": bool
    }
    return mapping.get(t, str)  # default to string if unknown


# ----------------------------
# Recursive function to build field definitions
# Returns (annotation_type, default_value) for create_model
#
# Important params:
# - allow_null: global toggle whether fields (where allowed) should be nullable
# - parent_is_array: whether this field is an item inside an array (affects nullability)
# ----------------------------
def build_field(field_def: Any, field_name: str = "", allow_null: bool = False, parent_is_array: bool = False):
    # 1. Primitive type string like "string" / "integer"
    if isinstance(field_def, str):
        base_py = python_type_from_user_type(field_def)

        # Array items must not be nullable => if parent_is_array, never make Optional
        if allow_null and not parent_is_array:
            py_type = Optional[base_py]
            default = None  # explicit None allowed (visible)
        else:
            # optional-by-omission: annotate as base type but give default None so field isn't required.
            # We'll avoid wrapping in Optional[...] (so schema generator won't automatically add "null")
            py_type = base_py
            default = None

        return (py_type, default)

    # 2. Enum type (e.g. {"enum": [...]})
    if isinstance(field_def, dict) and "enum" in field_def:
        # treat enums as strings at runtime
        enum_values = field_def["enum"]
        if allow_null and not parent_is_array:
            py_type = Optional[str]
            default = Field(default=None, description=f"Enum values: {enum_values}")
        else:
            py_type = str
            default = Field(default=None, description=f"Enum values: {enum_values}")
        return (py_type, default)

    # 3. Array type
    if isinstance(field_def, dict) and field_def.get("type") == "array":
        item_def = field_def.get("items")
        # When building item, mark parent_is_array=True so items never become nullable
        item_type, _ = build_field(item_def, field_name=field_name + "_item", allow_null=allow_null, parent_is_array=True)

        # Arrays are never Optional[List[...]] — use List[...] and default_factory=list
        py_type = List[item_type]
        default = Field(default_factory=list)
        return (py_type, default)

    # 4. Nested object
    # if isinstance(field_def, dict) and field_def.get("type") == "object":
    #     properties = field_def.get("properties", {})
    #     sub_model_name = (field_name.title().replace("_", "") or "Anonymous") + "SubModel"
    #     sub_model = build_pydantic_model(sub_model_name, properties, allow_null=allow_null)

    #     # If this object is an item in an array, DO NOT make it nullable
    #     if allow_null and not parent_is_array:
    #         py_type = Optional[sub_model]
    #         default = None  # visible null if absent and allow_null=True
    #     else:
    #         py_type = sub_model
    #         default = None  # optional-by-omission; not required, but not typed as Optional[...] (so schema won't auto-add null)

    #     return (py_type, default)
    
    # 4. Nested object
    if isinstance(field_def, dict) and field_def.get("type") == "object":
        properties = field_def.get("properties", {})
        sub_model_name = field_name.title().replace("_","") + "SubModel"
        sub_model = build_pydantic_model(sub_model_name, properties, allow_null=allow_null, include_fail_reason=False)
        py_type = sub_model   # <-- CHANGE IS HERE
        return (py_type, None)


    # Fallback — unknown shapes default to string behavior
    if allow_null and not parent_is_array:
        return (Optional[str], None)
    return (str, None)


# ----------------------------
# Main function: builds a dynamic Pydantic model from user schema
# - allow_null toggles whether fields can be nullable (visible null) when appropriate
# ----------------------------
def build_pydantic_model(model_name: str, fields: dict, allow_null: bool = False, include_fail_reason: bool = False):
    """
    model_name: name for the model
    fields: dict of user-defined schema
    allow_null: boolean that controls whether fields (where allowed) become nullable
    """
    model_fields = {}
    

    for key, val in fields.items():
        py_type, default = build_field(val, field_name=key, allow_null=allow_null, parent_is_array=False)
        # create_model expects (annotation, default)
        model_fields[key] = (py_type, default)
    
    # Inject "fail reason" only at root
    if include_fail_reason:
        if allow_null:
            model_fields["fail reason"] = (Optional[str], None)
        else:
            model_fields["fail reason"] = (str, None)

    return create_model(model_name, **model_fields)


# ----------------------------
# Convert Pydantic model -> OpenAI JSON Schema-like structure
# - allow_null controls whether properties (when not array items) should accept null
# - arrays never accept null (even if allow_null=True)
# - array items are resolved with in_array_item=True so they never get null added
# ----------------------------
def pydantic_to_jsonschema(model: Type[BaseModel], schema_name: str = None, allow_null: bool = False):
    """Convert a Pydantic BaseModel into OpenAI's JSON schema-like dict."""

    def resolve_type(py_type, in_array_item: bool = False):
        origin = get_origin(py_type)
        args = get_args(py_type)

        # Handle Optional / Union[..., None]
        if origin is Union and type(None) in args:
            # unwrap the non-none part, but keep note that the annotation explicitly included None
            non_none = [a for a in args if a is not type(None)][0]
            t = resolve_type(non_none, in_array_item=in_array_item)

            # If explicit Optional/Union with None, we must reflect that nullability.
            # However: we never add null to arrays (if in_array_item then t may be array)
            if isinstance(t.get("type"), str):
                if t["type"] != "array":
                    t["type"] = [t["type"], "null"]
            else:
                # t["type"] is a list
                if "null" not in t["type"] and "array" not in t["type"]:
                    t["type"].append("null")
            return t

        # List[T] (array)
        if origin is list or origin is List:
            # array items must never be nullable
            item_schema = resolve_type(args[0], in_array_item=True)
            return {
                "type": "array",
                "items": item_schema
            }

        # Nested Pydantic model
        if isinstance(py_type, type) and issubclass(py_type, BaseModel):
            return make_schema(py_type)

        # Primitive types
        if py_type is str:
            return {"type": "string"}
        if py_type is int:
            return {"type": "integer"}
        if py_type is float:
            return {"type": "number"}
        if py_type is bool:
            return {"type": "boolean"}

        # fallback
        return {"type": "string"}

    def make_schema(model_cls: Type[BaseModel]):
        schema = {
            "type": "object",
            "properties": {},
            # We'll compute "required" below using Pydantic's metadata
            "required": [],
            "additionalProperties": False
        }

        for field_name, field_info in model_cls.model_fields.items():
            field_type = field_info.annotation
            # top-level property resolution: not an array item
            json_type = resolve_type(field_type, in_array_item=False)

            # If allow_null is True, and this property is NOT an array, and the
            # json_type does not already allow null, add null to show "looked but not found".
            # BUT NEVER add null to arrays.
            t = json_type.get("type")
            if allow_null:
                if isinstance(t, str):
                    if t != "array":
                        json_type["type"] = [t, "null"]
                elif isinstance(t, list):
                    if "null" not in t and "array" not in t:
                        json_type["type"].append("null")

            schema["properties"][field_name] = json_type

            # Determine requiredness from Pydantic field metadata:
            # field_info.required is True when no default was provided (i.e., required)
            if getattr(field_info, "required", False):
                schema["required"].append(field_name)

        schema["required"] = list(schema["properties"].keys())

        return schema

    name = schema_name or model.__name__

    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "schema": make_schema(model),
            "strict": True
        }
    }


# ----------------------------
# Example usage
# ----------------------------
if __name__ == "__main__":
    # initial descriptive schema
    initial = {
        "cardholder_name": "string",
        "hobbies": {
            "type": "array",
            "items": "string"
        },
        "profile": {
            "type": "object",
            "properties": {
                "name": "string",
                "age": "integer"
            }
        },
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": "string",
                    "amount": "float",
                    "meta": {
                        "type": "object",
                        "properties": {
                            "id": "string",
                            "amount": "float"
                        }
                    }
                }
            }
        }
    }

    # Build Pydantic model with allow_null=False (default)
    # ModelNoNull = build_pydantic_model("StatementModelNoNull", initial, allow_null=False)
    # print("Pydantic model fields (no null):", ModelNoNull.model_fields.keys())
    # schema_no_null = pydantic_to_jsonschema(ModelNoNull, schema_name="StatementNoNull", allow_null=False)
    import json
    # print(json.dumps(schema_no_null, indent=2))

    # Build Pydantic model with allow_null=True (makes primitives/objects nullable when allowed,
    # but arrays and array items remain non-nullable)
    ModelWithNull = build_pydantic_model("StatementModelWithNull", initial, allow_null=False, include_fail_reason=True)
    schema_with_null = pydantic_to_jsonschema(ModelWithNull, schema_name="StatementWithNull", allow_null=False)
    print(json.dumps(schema_with_null, indent=2))
