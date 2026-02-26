# schemas.py
from pydantic import BaseModel
from typing import List, Optional
from ..models import ParsedOrder, OrderItem

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


# ai_client.py
from openai import OpenAI
from django.conf import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".log"]

def process_order_with_ai(email_body: str, attachments: list):
    """
    Sends email body + the original attachments to GPT-4o-mini as input files.
    Only PDFs, images, and text files are supported.
    """
    try:
        print("PROCESSING EMAIL WITH AI...")
        print('ATTACHMENTS:', attachments)

        # Base input containing the email body
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a dedicated Order Entry Clerk.\n"
                    "Your job is to analyze emails and files (PDFs, images, text files).\n"
                    "You must determine whether the provided content is a valid purchase order/invoice.\n"
                    "Extract data into the JSON schema and validate thoroughly. Do NOT guess.\n"
                    "If not a valid order, set fail_reason to why order is not valid, set is_valid_order=false and return null values."
                )
            },
            {
                "role": "user",
                "content": email_body.strip() or "(No email text provided)"
            }
        ]

        # Add file inputs
        for att in attachments:
            file_path = att["file_path"]
            
            file_path = f"media/{file_path}"
            print('FILE PATH:', file_path)
            
            ext = file_path.lower().split(".")[-1]

            if f".{ext}" not in SUPPORTED_EXTENSIONS:
                print('UNSUPPORTED EXTENSIONS FOUND')
                continue
            else:
                print('UNSUPPORTED EXTENSIONS NOT FOUND')
            
            uploaded = client.files.create(
                file=open(file_path, "rb"),
                purpose="user_data"
            )
            
            file_id = uploaded.id
            print('FILE ID:', file_id)

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id  # Raw file is streamed by SDK
                    }
                ]
            })
        
        # print('MESSAGES:', messages)
        
        # Add required keys to schema
        schema = pydantic_to_jsonschema(ParsedOrderSchema)
        # schema["additionalProperties"] = False
        # print('NEW SCHEMA:', schema)

        # AI call with structured outputs
        response = client.responses.create(
            model="gpt-4o-mini",
            # reasoning={"effort": "low"},
            # structured_outputs={"schema": ParsedOrderSchema},
            # structured_output=ParsedOrderSchema,
            input=messages,
            # text_format=ParsedOrderSchema
            text=schema
        )
        
        print('RESPONSE:', response)

        # return response.output_parsed
        return response.output[0].content[0].text
    
    except Exception as e:
        print('ERROR WHILE PROCESSING:', e)

def process_email(email_obj):
    parsed = process_order_with_ai(
        email_body=email_obj.body,
        attachments=email_obj.attachments
    )
    
    print('PARSED:', parsed)

    if not parsed.is_valid_order:
        email_obj.status = "not_order"
        email_obj.save()
        return False

    # Save valid order
    order = ParsedOrder.objects.create(
        email=email_obj,
        supplier=parsed.supplier,
        order_number=parsed.order_number,
        date=parsed.date,
        currency=parsed.currency,
        total_amount=parsed.total_amount,
        raw_json=parsed.dict()
    )

    # Save items
    for item in parsed.items or []:
        OrderItem.objects.create(
            order=order,
            sku=item.sku,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price
        )
    return True
