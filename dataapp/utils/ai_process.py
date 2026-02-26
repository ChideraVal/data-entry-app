import json
import logging
import time
from functools import wraps
from pydantic import ValidationError
from ..models import ExtractionResult
from django.db import IntegrityError
from .schema import pydantic_to_jsonschema, build_pydantic_model
from openai import OpenAI
from django.conf import settings
from .email_monitor import MAX_OPENAI_FILE_SIZE, format_bytes

logger = logging.getLogger("email_monitor")

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# -----------------------
# Constants / Config
# -----------------------

SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"]

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
def process_order_with_ai(email_body: str, attachments: list, environment):
    """
    Send email body + attachments to OpenAI and return the raw AI output text (string).
    This is marked critical: if it fails after retries, the calling code must NOT mark email processed.
    NOTE: file streaming and structured output usage kept exactly as requested.
    """

    logger.info("Starting AI processing for email.")
    logger.debug("Email body length: %d", len(email_body or ""))
    
    # DOCUMENT_TYPES = environment.document_types
    DOCUMENT_TYPES = settings.DEFAULT_DOCUMENT_TYPES
    print("DOCUMENT TYPES:", DOCUMENT_TYPES, '/'.join(DOCUMENT_TYPES), type(DOCUMENT_TYPES))
    
    UNIVERSAL_EXTRACTION_PROMPT = f"""
You are an advanced Structured Data Extraction AI.
Your job is to analyze emails and files (PDFs, images, text files, etc).
You must determine whether the provided content is a valid {'/'.join(DOCUMENT_TYPES)}.
Extract data into the JSON schema and validate thoroughly. Do NOT guess.
If provided content isn't exactly the document type you determined, set fail reason to the reason.
"""

    # Build base messages
    messages = [
        {"role": "system", "content": UNIVERSAL_EXTRACTION_PROMPT},
        {"role": "user", "content": email_body.strip() or "(No email text provided)"}
    ]

    # Attach files (preserve your existing logic and streaming approach)
    for att in attachments or []:
        # att expected: dict with keys "file_path" or "url" depending on your storage.
        file_path = att.get("file_path") or ""
        # In DEBUG you store local paths like "media/..."; keep same behavior:
        # if settings.DEBUG and not file_path.startswith("http"):
        #     file_path = f"media/{file_path}"

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
    environment_schema = environment.schema.schema_json
    PydanticModel = build_pydantic_model("ParseSchemaModel", environment_schema, allow_null=False, include_fail_reason=True)
    schema = pydantic_to_jsonschema(PydanticModel, "ParseSchema", allow_null=False)
    
    print("OPENAI SCHEMA:", schema)

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

def process_email(env_email_obj):
    """
    Process a single IncomingOrderEmail instance with AI.
    Option A (strict): if AI processing fails => do NOT mark email_obj.processed True.
    Return: True on success (and persisted), False otherwise.
    """
    
    # Proceed only if environment email has not been processed
    if ExtractionResult.objects.filter(environment_email=env_email_obj).exists():
        logger.info("AI parsing and parsed data creation already performed for environment email id=%s", getattr(env_email_obj, "id", None))
        return True
    
    email_obj = env_email_obj.internal_email
    
    # Fail automatically if email file size is more then MAX OPENAI FILE SIZE
    if email_obj.total_file_size > MAX_OPENAI_FILE_SIZE:
        logger.info(f"AI parsing failed for environment email id=%s because it's total file size ({format_bytes(email_obj.total_file_size)}) is greater than OPENAI limit ({format_bytes(MAX_OPENAI_FILE_SIZE)})", getattr(env_email_obj, "id", None))
        return False
    
    # email_obj = env_email_obj.internal_email
    logger.info("Starting AI parse for environment email id=%s subject='%s'", getattr(env_email_obj, "id", None), email_obj.subject)

    try:
        ai_output_text = process_order_with_ai(email_body=email_obj.body or "", attachments=email_obj.attachments or [], environment=env_email_obj.environment)
        logger.debug("AI raw output: %.1000s", ai_output_text[:1000] if ai_output_text else "")

    except CriticalRetryError as cre:
        # Option A: treat as permanent failure for this run — do not mark processed
        logger.error("Critical AI failure for environment email id=%s: %s", getattr(env_email_obj, "id", None), cre, exc_info=True)
        # Optionally attach failure reason to model (if you have fields)
        env_email_obj.status = "failed"
        env_email_obj.save(update_fields=["status"])
        return False

    except RetryError as re:
        # Non-critical final failure — per Option A we still treat AI failure as critical.
        logger.error("Non-critical AI retry error (treated as critical per Option A): %s", re, exc_info=True)
        return False

    except Exception as e:
        # Unexpected exceptions from AI call -> treat as critical
        logger.exception("Unexpected error calling AI for environment email id=%s: %s", getattr(env_email_obj, "id", None), e)
        return False

    # ai_output_text must be JSON parsable (your original flow)
    try:
        parsed_dict = json.loads(ai_output_text)
    except Exception as e:
        logger.exception("AI output JSON parse failed for environment email id=%s: %s", getattr(env_email_obj, "id", None), e)
        # Treat as critical — do NOT mark processed
        return False

    # Validate with DynamicModel (this can raise ValidationError)
    try:
        environment_schema = env_email_obj.environment.schema.schema_json
        PydanticModel = build_pydantic_model("ParseSchemaModel", environment_schema, allow_null=False, include_fail_reason=True)
        parsed_obj = PydanticModel(**parsed_dict)
    except ValidationError as ve:
        logger.error("AI output failed Pydantic validation for environment email id=%s: %s", getattr(env_email_obj, "id", None), ve, exc_info=True)
        # Strict mode -> do not mark processed
        return False

    # Passed validation — persist parsed result
    try:
        env_email_obj.status = 'successful'
        env_email_obj.save(update_fields=["status"])

        # Save parsed data record
        
        # raw_json = parsed_obj.model_dump_json()       
        raw_json = parsed_obj.model_dump()
        raw_json["Email ID"] = env_email_obj.id
        raw_json = json.dumps(raw_json)
        
        print('RAW JSON: ', raw_json)
        
        ExtractionResult.objects.create(
            environment=env_email_obj.environment,
            environment_email=env_email_obj,
            raw_json=raw_json
        )

        logger.info("AI parsing and saving succeeded for environment email id=%s", getattr(env_email_obj, "id", None))
        return True
    # Handle again just in case
    except IntegrityError as e:
        logger.exception("AI parsing succeeded but failed to save parsed data for environment email id=%s: %s because parsed data already exists for this environment email", getattr(env_email_obj, "id", None), e)
        return True
    except Exception as e:
        logger.exception("Failed to save parsed data for environment email id=%s: %s", getattr(env_email_obj, "id", None), e)
        # Treat as critical - do not mark processed (we already attempted to set processed True above;
        # but if saving ExtractionResult failed we should consider this run failed)
        # revert processed flag if needed:
        try:
            env_email_obj.status = 'failed'
            env_email_obj.save(update_fields=["status"])
        except Exception:
            logger.exception("Failed to revert status flag for environment email id=%s", getattr(env_email_obj, "id", None))
        return False


# -----------------------
# High-level uplaod processing
# -----------------------

def process_upload(env_upload_obj):
    """
    Process a single IncomingOrderEmail instance with AI.
    Option A (strict): if AI processing fails => do NOT mark email_obj.processed True.
    Return: True on success (and persisted), False otherwise.
    """
    
    # Proceed only if environment email has not been processed
    if ExtractionResult.objects.filter(environment_upload=env_upload_obj).exists():
        logger.info("AI parsing and parsed data creation already performed for environment upload id=%s", getattr(env_upload_obj, "id", None))
        return True
    
    # Fail automatically if upload file size is more then MAX OPENAI FILE SIZE
    if env_upload_obj.total_file_size > MAX_OPENAI_FILE_SIZE:
        logger.info(f"AI parsing failed for environment upload id=%s because it's total file size ({format_bytes(env_upload_obj.total_file_size)}) is greater than OPENAI limit ({format_bytes(MAX_OPENAI_FILE_SIZE)})", getattr(env_upload_obj, "id", None))
        return False
    
    # upload_obj = env_upload_obj.name
    logger.info("Starting AI parse for environment upload id=%s name='%s'", getattr(env_upload_obj, "id", None), env_upload_obj.name)

    try:
        ai_output_text = process_order_with_ai(email_body="", attachments=env_upload_obj.attachments or [], environment=env_upload_obj.environment)
        logger.debug("AI raw output: %.1000s", ai_output_text[:1000] if ai_output_text else "")
    except CriticalRetryError as cre:
        # Option A: treat as permanent failure for this run — do not mark processed
        logger.error("Critical AI failure for environment upload id=%s: %s", getattr(env_upload_obj, "id", None), cre, exc_info=True)
        # Optionally attach failure reason to model (if you have fields)
        env_upload_obj.status = "failed"
        env_upload_obj.save(update_fields=["status"])
        return False

    except RetryError as re:
        # Non-critical final failure — per Option A we still treat AI failure as critical.
        logger.error("Non-critical AI retry error (treated as critical per Option A): %s", re, exc_info=True)
        return False

    except Exception as e:
        # Unexpected exceptions from AI call -> treat as critical
        logger.exception("Unexpected error calling AI for environment upload id=%s: %s", getattr(env_upload_obj, "id", None), e)
        return False

    # ai_output_text must be JSON parsable (your original flow)
    try:
        parsed_dict = json.loads(ai_output_text)
    except Exception as e:
        logger.exception("AI output JSON parse failed for environment upload id=%s: %s", getattr(env_upload_obj, "id", None), e)
        # Treat as critical — do NOT mark processed
        return False

    # Validate with DynamicModel (this can raise ValidationError)
    try:
        environment_schema = env_upload_obj.environment.schema.schema_json
        PydanticModel = build_pydantic_model("ParseSchemaModel", environment_schema, allow_null=False, include_fail_reason=True)
        parsed_obj = PydanticModel(**parsed_dict)
    except ValidationError as ve:
        logger.error("AI output failed Pydantic validation for environment upload id=%s: %s", getattr(env_upload_obj, "id", None), ve, exc_info=True)
        # Strict mode -> do not mark processed
        return False

    # Passed validation — persist parsed result
    try:
        env_upload_obj.status = 'successful'
        env_upload_obj.save(update_fields=["status"])

        # Save parsed data record
        
        # raw_json = parsed_obj.model_dump_json()       
        raw_json = parsed_obj.model_dump()
        raw_json["Upload ID"] = env_upload_obj.id
        raw_json = json.dumps(raw_json)
        
        print('RAW JSON: ', raw_json)
        
        ExtractionResult.objects.create(
            environment=env_upload_obj.environment,
            environment_upload=env_upload_obj,
            raw_json=raw_json
        )

        logger.info("AI parsing and saving succeeded for environment upload id=%s", getattr(env_upload_obj, "id", None))
        return True
    # Handle again just in case
    except IntegrityError as e:
        logger.exception("AI parsing succeeded but failed to save parsed data for environment upload id=%s: %s because parsed data already exists for this environment upload", getattr(env_upload_obj, "id", None), e)
        return True
    except Exception as e:
        logger.exception("Failed to save parsed data for environment upload id=%s: %s", getattr(env_upload_obj, "id", None), e)
        # Treat as critical - do not mark processed (we already attempted to set processed True above;
        # but if saving ExtractionResult failed we should consider this run failed)
        # revert processed flag if needed:
        try:
            env_upload_obj.status = 'failed'
            env_upload_obj.save(update_fields=["status"])
        except Exception:
            logger.exception("Failed to revert status flag for environment upload id=%s", getattr(env_upload_obj, "id", None))
        return False
