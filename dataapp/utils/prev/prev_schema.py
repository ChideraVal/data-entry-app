from pydantic import BaseModel
from typing import List, Optional

# HARD CODED SCHEMA CLASS

class Item(BaseModel):
    sku: Optional[str]
    description: Optional[str]
    quantity: Optional[int]
    unit_price: Optional[float]
    total_price: Optional[float]

class ParsedOrderSchema(BaseModel):
    is_valid_order: bool
    supplier: Optional[str]
    fail_reason: Optional[str]
    order_number: Optional[str]
    date: Optional[str]
    currency: Optional[str]
    total_amount: Optional[float]
    items: Optional[List[Item]]


# CONVERT JSON OBJECT TO PYDANTIC SCHEMA CLASS 

from pydantic import BaseModel, create_model, Field
from typing import List, Optional, Union

# ----------------------------
# Helper: Convert user type string → Python type
# ----------------------------
def python_type_from_user_type(t: str):
    mapping = {
        "string": str,
        "float": float,
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



user_schema = {
    "name": "InvoiceSchema",
    "fields": {
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
}

# user_schema = {
#     "name": "CardSchema",
    # "fields": {
    #     "fail_reason": "string",
    #     "account_info": {
    #         "type": "object",
    #         "properties": {
    #         "cardholder_name": "string",
    #         "card_last4": "string",
    #         "issuer_name": "string",
    #         "issuer_contact": "string",
    #         "statement_period": {
    #             "type": "object",
    #             "properties": {
    #                 "start_date": "string",
    #                 "end_date": "string"
    #             }
    #         }
    #         }
    #     },

    #     "summary": {
    #         "type": "object",
    #         "properties": {
    #         "previous_balance": "number",
    #         "payments": "number",
    #         "credits": "number",
    #         "purchases": "number",
    #         "fees": "number",
    #         "interest": "number",
    #         "new_balance": "number",
    #         "minimum_payment_due": "number",
    #         "payment_due_date": "string"
    #         }
    #     },

    #     "transactions": {
    #         "type": "array",
    #         "items": {
    #         "type": "object",
    #         "properties": {
    #             "transaction_date": "string",
    #             "posted_date": "string",
    #             "merchant_name": "string",
    #             "merchant_location": "string",
    #             "amount": "number",
    #             "currency": "string",
    #             "type": "string",
    #             "category": "string",
    #             "exchange_rate": "number"
    #         }
    #         }
    #     },

    #     "fees": {
    #         "type": "array",
    #         "items": {
    #         "type": "object",
    #         "properties": {
    #             "description": "string",
    #             "amount": "number",
    #             "date": "string"
    #         }
    #         }
    #     },

    #     "interest_charges": {
    #         "type": "array",
    #         "items": {
    #         "type": "object",
    #         "properties": {
    #             "type": "string",
    #             "amount": "number",
    #             "apr": "number"
    #         }
    #         }
    #     },

    #     "rewards": {
    #         "type": "object",
    #         "properties": {
    #         "points_earned": "number",
    #         "points_redeemed": "number",
    #         "current_points_balance": "number",
    #         "cashback_earned": "number"
    #         }
    #     },

    #     "notices": {
    #         "type": "array",
    #         "items": "string"
    #     }
    # }
# }

DynamicModel = build_pydantic_model(
    user_schema["name"], 
    user_schema["fields"]
)


# CONVERT PYDANTIC SCHEMA CLASS TO OPENAI SCHEMA

from pydantic import BaseModel
from typing import get_origin, get_args, Union, Optional
import sys

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

            # Convert e.g. "string" → ["string", "null"]
            if isinstance(t_type, str):
                t["type"] = [t_type, "null"]
            else:
                t["type"].append("null")

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

# o = pydantic_to_jsonschema(DynamicModel)
# print(o)



# file_bytes = base64.b64decode(data)

# directory = "my_email_attachments"
# res = cloudinary.uploader.upload(file_bytes, folder=directory)
# public_url = res.get("secure_url") or res.get("url")
# # Optionally: set saved_path to Cloudinary public_id or returned path
# saved_path = res.get("public_id", saved_path)
# print('PUBLIC URL:',saved_path)