from pydantic import BaseModel, create_model, Field
from typing import List, Optional, Union, Any
from typing import get_origin, get_args, Union, Optional


# ----------------------------
# Helper: Convert user type string → Python type
# ----------------------------
def python_type_from_user_type(t: str):
    mapping = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool
    }
    return mapping.get(t, str)  # default to string if unknown

# ----------------------------
# Recursive function to build field definitions
# Returns (type, default value) for create_model
# ----------------------------
def build_field(field_def: dict, field_name: str = ""):
    # 1. Primitive type
    if isinstance(field_def, str):
        py_type = Optional[python_type_from_user_type(field_def)]
        return (py_type, None)

    # 2. Enum type (if user provides "enum": ["val1", "val2"])
    if isinstance(field_def, dict) and "enum" in field_def:
        enum_values = field_def["enum"]
        py_type = Optional[str]  # enum is string-based
        return (py_type, Field(default=None, description=f"Enum values: {enum_values}"))

    # 3. Array type
    if isinstance(field_def, dict) and field_def.get("type") == "array":
        item_def = field_def.get("items")
        item_type, _ = build_field(item_def, field_name=field_name+"_item")
        py_type = Optional[List[item_type]]
        return (py_type, None)

    # 4. Nested object
    if isinstance(field_def, dict) and field_def.get("type") == "object":
        # recursive call to build sub-model
        properties = field_def.get("properties", {})
        sub_model_name = field_name.title().replace("_","") + "SubModel"
        sub_model = build_pydantic_model(sub_model_name, properties)
        py_type = Optional[sub_model]
        return (py_type, None)

    # fallback
    return (Optional[str], None)

# ----------------------------
# Main function: builds a dynamic Pydantic model from user schema
# ----------------------------
def build_pydantic_model(model_name: str, fields: dict):
    """
    model_name: string name of the model
    fields: dict of user-defined schema
            example:
            {
                "invoice_id": "string",
                "amount": "number",
                "items": {
                    "type": "array",
                    "items": {
                        "product": "string",
                        "qty": "integer"
                    }
                }
            }
    """
    model_fields = {}

    for key, val in fields.items():
        py_type, default = build_field(val, field_name=key)
        model_fields[key] = (py_type, default)

    # Create and return the dynamic Pydantic model
    return create_model(model_name, **model_fields)


def pydantic_to_jsonschema(model: type[BaseModel], schema_name: str = None):
    """Convert a Pydantic BaseModel into OpenAI's JSON schema format."""
    
    def resolve_type(py_type):
        origin = get_origin(py_type)
        args = get_args(py_type)

        # Optional[T] → Union[T, None]
        if origin is Union and type(None) in args:
            non_none = [a for a in args if a is not type(None)][0]
            t = resolve_type(non_none)
            t_type = t.get("type")
            print('TYPE:', t_type)

            # Convert e.g. "string" → ["string", "null"]
            if isinstance(t_type, str):
                t["type"] = [t_type, "null"]
            else:
                t["type"].append("null")
            
            print('TYPE:', t_type, " ---- ", t["type"])

            return t

        # List[T]
        if origin is list or origin is list:
            return {
                "type": "array",
                "items": resolve_type(args[0])
            }

        # Nested model
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

        return {"type": "string"}  # fallback

    def make_schema(model_cls):
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        }

        for field_name, field in model_cls.model_fields.items():
            field_type = field.annotation

            json_type = resolve_type(field_type)

            schema["properties"][field_name] = json_type

            # Anything not Optional goes into required
            # origin = get_origin(field_type)
            # args = get_args(field_type)
            # if not (origin is Union and type(None) in args):
            #     schema["required"].append(field_name)
        
        # NEW LOGIC: all keys become required
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
    # Example: user-defined schema (from form or JSON input)
    user_schema = {
        "data": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "invoice_id": "string",
                    "customer": "string",
                    "amount": "number",
                    "paid": "boolean",
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product": "string",
                                "qty": "integer",
                                "price": "number",
                                "in_stock": "boolean"
                            }
                        }
                    }
                }
            }
        }
    }

    # # Build dynamic Pydantic model
    # DynamicModel = build_pydantic_model("InvoiceSchema", user_schema)

    # # Inspect the model class
    # print(DynamicModel)
    # print(
    #     pydantic_to_jsonschema(DynamicModel)
    # )

    # Instantiate the model
    # obj = DynamicModel(
    #     invoice_id="INV001",
    #     customer="Alice",
    #     amount=1200.5,
    #     paid=True,
    #     items=[
    #         {"product": "Pen", "qty": 10, "price": 2.5, "in_stock": True},
    #         {"product": "Notebook", "qty": 5, "price": 5.0, "in_stock": False}
    #     ]
    # )

    # # Print model as dict
    # print(obj.model_dump())


# from typing import get_origin, get_args, Union, Optional

# d
# obj = '{"invoice_id":false,"supplier":null,"fail_reason":"The content does not contain any purchase order or invoice details.","order_number":null,"date":null,"currency":null,"total_amount":null,"items":null}'
# validated = ParsedOrderModel.model_validate(json.loads(obj), strict=True)
# print("validated:", validated)


"""
validating json data (done)
file urls for gpt AI (done)
allowing image inputs (done)
uploading files to cloudinary (done)
processing multiple data / general processing prompt (done)
validating user-defined json schema (done)
validating openai file size (done)

"""


"""
You are an advanced Structured Data Extraction AI.
Your job is to analyze emails and files (PDFs, images, text files, etc).
You must determine the document type (card statement, invoice, purchase order, etc) and whether the provided content matches the determined document type.
Extract structured data from the email/document exactly following the provided JSON schema. Do NOT guess or hallucinate.
Missing or unclear values must be null.
Never add fields not defined in the schema or remove fields defined in the schema.
If provided content does not match determined document type, set fail_reason to why you think so, and return null values.
"""

s = {
    "orders": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                # "is_valid_order": "boolean",
                "supplier": "string",
                "fail_reason": "string",
                "document_type": "string",
                "order_number": "string",
                "date": "string",
                "currency": "string",
                "total_amount": "float",
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": "string",
                            "description": "string",
                            "quantity": "integer",
                            "unit_price": "float",
                            "total_price": "float"
                        }
                    }
                }
            }
        }
    }
}

# Build dynamic Pydantic model
DynamicModel = build_pydantic_model("InvoiceSchema", s)

# Inspect the model class
print(DynamicModel)
print(
    pydantic_to_jsonschema(DynamicModel)
)

def validate_schema_json(schema_json: dict):
    if not isinstance(schema_json, dict) or not schema_json:
        raise ValueError("Schema must be a non-empty object")

    def walk(node):
        if isinstance(node, str):
            return
        if isinstance(node, dict):
            t = node.get("type")
            if t == "object":
                props = node.get("properties")
                if not props or not isinstance(props, dict):
                    raise ValueError("Object must have at least one property")
                for v in props.values():
                    walk(v)
            elif t == "array":
                if "items" not in node:
                    raise ValueError("Array must define items")
                walk(node["items"])
            else:
                raise ValueError(f"Invalid type: {t}")

    for value in schema_json.values():
        walk(value)

# try:
#     # s = {}  
#     validate_schema_json(s)
# except Exception as e:
#     print(e)



"""
upload/email id
fail reason
rename uploads
schema UI updates (
    collapsible fields,
    button text
)

Result review updates (
    button text
    shape json reuse
    action buttons (approve, save, delete, etc)
)
"""