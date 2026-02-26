# schemas.py (refactored)
import json
import logging
import time
from functools import wraps
from datetime import datetime

from pydantic import ValidationError

from ..models import ParsedData
from .schema import pydantic_to_jsonschema, build_pydantic_model, DynamicModel

# AI client
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger("email_monitor")

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# -----------------------
# Constants / Config
# -----------------------

SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"]

DOCUMENT_TYPES = [
    "invoice",
    "purchase order",
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

# Use a slice of documents to parse (kept from your code)
DOCUMENTS_TO_PARSE = DOCUMENT_TYPES[0:8]
UNIVERSAL_EXTRACTION_PROMPT = f"""
You are an advanced Structured Data Extraction AI.
Your job is to analyze emails and files (PDFs, images, text files, etc).
You must determine whether the provided content is a valid {'/'.join(DOCUMENTS_TO_PARSE)}.
Extract data into the JSON schema and validate thoroughly. Do NOT guess.
If provided content isn't exactly the document type you determined, set fail_reason to the reason, and return null values.
"""

# -----------------------
# Retry + Exceptions
# -----------------------

class RetryError(Exception):
    """Raised for non-critical retry failures (we may still save the email)."""
    pass

class CriticalRetryError(Exception):
    """Raised for critical retry failures (email must NOT be marked processed)."""
    pass

def retry(max_retries=3, delay=2, backoff=2, critical=False):
    """
    Retry decorator with exponential backoff.
    - If critical=True: raises CriticalRetryError after exhausting retries.
    - If critical=False: raises RetryError after exhausting retries.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            last_exc = None

            while attempt < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    attempt += 1
                    logger.warning(
                        f"[AI Retry {attempt}/{max_retries}] {func.__name__} failed: {e}"
                    )
                    if attempt >= max_retries:
                        logger.error(f"[AI FAILED] {func.__name__} exceeded {max_retries} attempts.")
                        if critical:
                            raise CriticalRetryError(f"Critical function '{func.__name__}' failed after retries.") from e
                        else:
                            raise RetryError(f"Function '{func.__name__}' failed after retries.") from e
                    time.sleep(current_delay)
                    current_delay *= backoff
            # Shouldn't reach here
            if critical:
                raise CriticalRetryError(f"Critical function '{func.__name__}' failed (unexpected).") from last_exc
            else:
                raise RetryError(f"Function '{func.__name__}' failed (unexpected).") from last_exc

        return wrapper
    return decorator

# -----------------------
# AI processing
# -----------------------

@retry(max_retries=3, delay=2, backoff=2, critical=True)
def process_order_with_ai(email_body: str, attachments: list):
    """
    Send email body + attachments to OpenAI and return the raw AI output text (string).
    This is marked critical: if it fails after retries, the calling code must NOT mark email processed.
    NOTE: file streaming and structured output usage kept exactly as requested.
    """

    logger.info("Starting AI processing for email.")
    logger.debug("Email body length: %d", len(email_body or ""))

    # Build base messages
    messages = [
        {"role": "system", "content": UNIVERSAL_EXTRACTION_PROMPT},
        {"role": "user", "content": email_body.strip() or "(No email text provided)"}
    ]

    # Attach files (preserve your existing logic and streaming approach)
    for att in attachments or []:
        # att expected: dict with keys "file_path" or "url" depending on your storage.
        file_path = att.get("file_path") or att.get("url") or ""
        # In DEBUG you store local paths like "media/..."; keep same behavior:
        if settings.DEBUG and not file_path.startswith("http"):
            file_path = f"media/{file_path}"

        logger.debug("Preparing attachment for AI: %s", file_path)

        ext = "." + file_path.lower().split(".")[-1] if "." in file_path else ""
        if ext and ext not in SUPPORTED_EXTENSIONS:
            logger.info("Skipping unsupported attachment extension: %s", ext)
            continue

        # For images (non-pdf/txt), you used input_image
        if ext not in [".pdf", ".txt"]:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": file_path,
                        "detail": "low"
                    }
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_url": file_path
                    }
                ]
            })

    # Convert Pydantic dynamic model to jsonschema (you said keep this behavior)
    schema = pydantic_to_jsonschema(DynamicModel)

    logger.debug("Sending request to OpenAI (model=gpt-5-nano). Schema length: %d", len(schema))

    # The call below keeps your original usage; we wrap in retry decorator so network/AI failures are retried.
    response = client.responses.create(
        model="gpt-5-nano",
        input=messages,
        text=schema
    )

    logger.debug("OpenAI response received: %s", getattr(response, "status", "no-status"))

    # Prefer response.output_text if available (your original code used it)
    # We will validate existence and return string - caller will parse JSON.
    ai_text = None
    try:
        # Many responses have output_text; if not fall back to other fields
        if hasattr(response, "output_text"):
            ai_text = response.output_text
        else:
            # fallback: try to extract textual output from response.output list
            out = getattr(response, "output", None)
            if out and isinstance(out, list) and len(out) > 0:
                # find first textual content
                first = out[0]
                content = first.get("content") if isinstance(first, dict) else None
                if content and isinstance(content, list) and len(content) > 0:
                    ai_text = content[0].get("text") if isinstance(content[0], dict) else None

    except Exception as e:
        logger.exception("Error while extracting text from AI response: %s", e)
        # Treat as critical (per option A)
        raise CriticalRetryError("AI returned unreadable response") from e

    if not ai_text:
        logger.error("AI returned no textual output; failing (critical). Response: %s", response)
        raise CriticalRetryError("AI returned no output text")

    logger.info("AI processing completed successfully (text length: %d).", len(ai_text))
    return ai_text


# -----------------------
# High-level email processing
# -----------------------

def process_email(email_obj):
    """
    Process a single IncomingOrderEmail instance with AI.
    Option A (strict): if AI processing fails => do NOT mark email_obj.processed True.
    Return: True on success (and persisted), False otherwise.
    """

    logger.info("Starting AI parse for email id=%s subject='%s'", getattr(email_obj, "id", None), email_obj.subject)

    try:
        ai_output_text = process_order_with_ai(email_body=email_obj.body or "", attachments=email_obj.attachments or [])
        logger.debug("AI raw output: %.1000s", ai_output_text[:1000] if ai_output_text else "")

    except CriticalRetryError as cre:
        # Option A: treat as permanent failure for this run — do not mark processed
        logger.error("Critical AI failure for email id=%s: %s", getattr(email_obj, "id", None), cre, exc_info=True)
        # Optionally attach failure reason to model (if you have fields)
        # email_obj.ai_fail_reason = str(cre)
        # email_obj.save(update_fields=["ai_fail_reason"])
        return False

    except RetryError as re:
        # Non-critical final failure — per Option A we still treat AI failure as critical.
        logger.error("Non-critical AI retry error (treated as critical per Option A): %s", re, exc_info=True)
        return False

    except Exception as e:
        # Unexpected exceptions from AI call -> treat as critical
        logger.exception("Unexpected error calling AI for email id=%s: %s", getattr(email_obj, "id", None), e)
        return False

    # ai_output_text must be JSON parsable (your original flow)
    try:
        parsed_dict = json.loads(ai_output_text)
    except Exception as e:
        logger.exception("AI output JSON parse failed for email id=%s: %s", getattr(email_obj, "id", None), e)
        # Treat as critical — do NOT mark processed
        return False

    # Validate with DynamicModel (this can raise ValidationError)
    try:
        parsed_obj = DynamicModel(**parsed_dict)
    except ValidationError as ve:
        logger.error("AI output failed Pydantic validation for email id=%s: %s", getattr(email_obj, "id", None), ve, exc_info=True)
        # Strict mode -> do not mark processed
        return False

    # Passed validation — persist parsed result
    try:
        email_obj.status = 'successful'
        email_obj.save(update_fields=["status"])

        # Save parsed data record
        ParsedData.objects.create(
            email=email_obj,
            raw_json=parsed_obj.model_dump_json()
        )

        logger.info("AI parsing and saving succeeded for email id=%s", getattr(email_obj, "id", None))
        return True

    except Exception as e:
        logger.exception("Failed to save parsed data for email id=%s: %s", getattr(email_obj, "id", None), e)
        # Treat as critical - do not mark processed (we already attempted to set processed True above;
        # but if saving ParsedData failed we should consider this run failed)
        # revert processed flag if needed:
        try:
            email_obj.status = 'failed'
            email_obj.save(update_fields=["status"])
        except Exception:
            logger.exception("Failed to revert status flag for email id=%s", getattr(email_obj, "id", None))
        return False
