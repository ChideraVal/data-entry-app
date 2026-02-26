# schemas.py
from ..models import ParsedData
from .schema import pydantic_to_jsonschema, build_pydantic_model, DynamicModel
from pydantic import ValidationError
import json
import logging
from functools import wraps
import time

logger = logging.getLogger("email_monitor")

# ai_client.py
from openai import OpenAI
from django.conf import settings

# -------------------
# RETRY DECORATOR
# -------------------
def retry(max_retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    logger.warning(
                        f"[Retry {retries}/{max_retries}] {func.__name__} failed: {e}"
                    )
                    if retries >= max_retries:
                        logger.error(
                            f"[FAILED] {func.__name__} exceeded max retries."
                        )
                        raise
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"]

DOCUMENT_TYPES = [
    "invoice",
    "receipt",
    "bank statement",
    "credit card statement",
    "utility bill",
    "tax document",
    "medical report",
    "prescription",
    "lab test result",
    "insurance policy document",
    "insurance claim form",
    "employment contract",
    "offer letter",
    "salary slip",
    "purchase order",
    "delivery note",
    "shipping label",
    "packing slip",
    "rental agreement",
    "lease contract",
    "legal notice",
    "court document",
    "passport scan",
    "id card scan",
    "driver license scan",
    "boarding pass",
    "travel itinerary",
    "hotel booking confirmation",
    "flight ticket",
    "medical bill",
    "donation receipt",
    "academic transcript",
    "certificate",
    "warranty document",
    "maintenance report",
    "test report",
    "safety inspection report",
    "handwritten notes",
    "meeting minutes",
    "printed letter",
    "business card",
    "expense report",
    "shopping list",
    "to do list",
    "delivery receipt",
    "service invoice",
    "property deed",
    "bank alert document",
    "payment confirmation",
    "transaction summary",
    "quote or estimate",
    "research paper",
    "brochure or flyer"
]

DOCUMENTS_TO_PARSE = DOCUMENT_TYPES[4:8]
print('DOCUMENTS_TO_PARSE:',DOCUMENTS_TO_PARSE)
print('DOCUMENTS_TO_PARSE SLASH:', '/'.join(DOCUMENTS_TO_PARSE))


UNIVERSAL_EXTRACTION_PROMPT = f"""
You are an advanced Structured Data Extraction AI.
Your job is to analyze emails and files (PDFs, images, text files, etc).
You must determine whether the provided content is a valid {'/'.join(DOCUMENTS_TO_PARSE)}.
Extract data into the JSON schema and validate thoroughly. Do NOT guess.
If provided content isn't exactly the document type you determined, set fail_reason to the reason, and return null values.
"""

@retry(max_retries=3)
def process_order_with_ai(email_body: str, attachments: list):
    """
    Sends email body + the original attachments to GPT-5-nano as input files.
    Only PDFs, images, and text files are supported.
    """
    try:
        print("PROCESSING EMAIL WITH AI...")
        print('ATTACHMENTS:', attachments)

        # Base input containing the email body
        messages = [
            {
                "role": "system",
                "content": UNIVERSAL_EXTRACTION_PROMPT
            },
            {
                "role": "user",
                "content": email_body.strip() or "(No email text provided)"
            }
        ]

        # Add file inputs
        for att in attachments:
            file_path = att["file_path"]
            
            if settings.DEBUG:
                file_path = f"media/{file_path}"
                
            print('FILE PATH:', file_path)
            
            ext = file_path.lower().split(".")[-1]

            if f".{ext}" not in SUPPORTED_EXTENSIONS:
                print('UNSUPPORTED EXTENSIONS FOUND')
                continue
            else:
                print('UNSUPPORTED EXTENSIONS NOT FOUND')
            
            # CREATE MESSAGE BASED ON FILE TYPE (IMAGE/PDF/TXT)
            if f".{ext}" not in [".pdf", ".txt"]:
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": file_path,  # Raw file is streamed by SDK
                            "detail": "low"
                        }
                    ]
                })
            else:
                # uploaded = client.files.create(
                #     file=open(file_path, "rb"),
                #     purpose="user_data"
                # )
                
                # file_id = uploaded.id
                # print('FILE ID:', file_id)

                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            # "file_id": file_id  # Raw file is streamed by SDK
                            "file_url": file_path  # Raw file is streamed by SDK
                        }
                    ]
                })
        
        # print('MESSAGES:', messages)
        
        schema = pydantic_to_jsonschema(DynamicModel)

        # AI call with structured outputs
        response = client.responses.create(
            model="gpt-5-nano",
            # reasoning={"effort": "low"},
            # structured_outputs={"schema": ParsedOrderSchema},
            # structured_output=ParsedOrderSchema,
            input=messages,
            # text_format=ParsedOrderSchema
            text=schema
        )
        
        print('RESPONSE:', response)

        # return response.output_parsed
        # if f".{ext}" not in [".pdf", ".txt"]:
        return response.output_text
        # else:
        #     return response.output[0].content[0].text
    
    except Exception as e:
        print('ERROR WHILE PROCESSING:', e)

def process_email(email_obj):
    ai_output = process_order_with_ai(
        email_body=email_obj.body,
        attachments=email_obj.attachments
    )
    
    print('PARSED:', ai_output)

    parsed_dict = json.loads(ai_output)
    print("TYPE:",type(parsed_dict))
    
    # Validate + convert to Pydantic model instance
    try:
        parsed = DynamicModel(**parsed_dict)
        print("OBJ:",parsed)
    except ValidationError as e:
        print("VALIDATION FAILED:", e.errors())
        return False

    # Save valid data
    try:
        email_obj.processed = True
        email_obj.save()
        
        ParsedData.objects.create(
            email=email_obj,
            # supplier=parsed.supplier,
            # order_number=parsed.order_number,
            # date=parsed.date,
            # currency=parsed.currency,
            # total_amount=parsed.total_amount,
            raw_json=parsed.model_dump_json()
        )

        return True
    except Exception as e:
        print('EXCEPTION:', e)
