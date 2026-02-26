import imaplib
import email
import os
import time
import logging
from functools import wraps
from email.header import decode_header
from email.utils import parsedate_to_datetime
from django.conf import settings
from ..models import InternalEmail, Environment, EnvironmentEmail
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import cloudinary.uploader
from django.db import transaction, IntegrityError
import json

logger = logging.getLogger("email_monitor")

# ============================================================
# CONFIGURATION
# ============================================================

# ALLOWED_FILE_TYPES = ["pdf", "png", "jpg", "jpeg", "webp", "txt"]

# ALLOWED_SENDERS = ["fluxlite224@gmail.com"]
# ALLOWED_SUBJECT_KEYWORDS = []
# BLOCKED_SUBJECT_KEYWORDS = []
# REQUIRE_ATTACHMENT = False

# SINCE_DATE = datetime(2025, 10, 1)
MAX_OPENAI_FILE_SIZE = 1024 ** 2 * 50 # 50MB


# ============================================================
# NEW CUSTOM RETRY EXCEPTIONS
# ============================================================

class RetryError(Exception):
    """Non-critical retry failure."""
    pass

class CriticalRetryError(Exception):
    """Critical retry failure — abort processing current email."""
    pass

# ============================================================
# ENHANCED RETRY DECORATOR
# ============================================================

def retry(max_retries=3, delay=1, backoff=2, critical=False):
    """
    critical=True → raise CriticalRetryError
    critical=False → raise RetryError
    """
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
                        logger.error(f"[FAILED] {func.__name__} exceeded max retries.")

                        if critical:
                            raise CriticalRetryError(
                                f"Critical function '{func.__name__}' failed permanently."
                            ) from e
                        else:
                            raise RetryError(
                                f"Function '{func.__name__}' failed permanently."
                            ) from e

                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator

# ============================================================
# UTILITIES
# ============================================================

def safe_decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value or ""

def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)

def format_bytes(size):
    """
    Convert a size in bytes to a human-readable string in KB, MB, or GB.
    """
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 ** 3:
        return f"{size / (1024 ** 2):.2f} MB"
    else:
        return f"{size / (1024 ** 3):.2f} GB"
    
# ============================================================
# ATTACHMENT SAVER — CRITICAL OPERATION
# ============================================================

@retry(max_retries=3, critical=True)
def save_attachment(filename, data, env_config):
    base, ext = os.path.splitext(filename)
    ext = ext[1:].lower()

    if ext not in env_config["ALLOWED_FILE_TYPES"]:
        logger.warning(f"Rejected attachment '{filename}' — unsupported file type.")
        # return None
        return None, None

    # ---------------- SAVE LOCALLY ----------------
    counter = 1
    unique_filename = filename

    while default_storage.exists(f"local_email_attachments/{unique_filename}"):
        unique_filename = f"{base}_{counter}.{ext}"
        counter += 1

    # If DEBUG: save locally
    # if settings.DEBUG:
    path = default_storage.save(f"local_email_attachments/{unique_filename}", ContentFile(data))
    logger.info(f"Saved attachment locally '{filename}' → {path}")
    # return path
    
    # Check if locally save file exceeds max size limit
    from pathlib import Path
    MAX_SIZE_MB = 200
    file_path = Path(f"media/{path}")
    print("FILE PATH: ", file_path)
    
    if not file_path.exists():
        print("File ({unique_filename}) does not exist")
        logger.warning("File ({unique_filename}) does not exist")
        return None, None
    
    size_mb = file_path.stat().st_size / (1024 * 1024)
    
    if size_mb > MAX_SIZE_MB:
        print(f"File ({unique_filename}) too large ({size_mb} MB). Maxsize allowed is {MAX_SIZE_MB} MB")
        logger.warning(f"File ({unique_filename}) too large ({size_mb} MB). Maxsize allowed is {MAX_SIZE_MB} MB")
        # Delete the file if it exceeds max size
        try:
            file_path.unlink(missing_ok=True) # Python 3.8+
        except IsADirectoryError:
            raise ValueError("Path points to a directory, not a file.")
        
        return None, None
    
    # Delete the file if it doesn't exceed max size
    try:
        file_path.unlink(missing_ok=True) # Python 3.8+
    except IsADirectoryError:
        raise ValueError("Path points to a directory, not a file.")

    # ---------------- END ----------------
    

    # Production → Cloudinary
    directory = "email_attachments"

    resource_type = "image"
    if ext in ["pdf", "txt"]:
        resource_type = "raw"

    res = cloudinary.uploader.upload(
        data,
        filename=unique_filename,
        folder=directory,
        resource_type=resource_type,
        use_filename=True
    )

    public_url = res.get("secure_url") or res.get("url")
    file_size = res.get("bytes")
    logger.info(f"Saved attachment '{filename}' → {public_url}")
    return public_url, file_size

# ============================================================
# IMAP LOGIN / FETCH — CRITICAL
# ============================================================

@retry(max_retries=3, critical=True)
def imap_login(env_config):
    imap = imaplib.IMAP4_SSL(env_config['IMAP_HOST'])
    imap.login(env_config['IMAP_EMAIL'], env_config['IMAP_PASSWORD'])
    logger.info("Successfully connected to IMAP server.")
    return imap

@retry(max_retries=2, critical=True)
def fetch_email(imap, email_id):
    _, msg_data = imap.fetch(email_id, "(BODY.PEEK[])")
    return email.message_from_bytes(msg_data[0][1])

# ============================================================
# IMAP SEARCH QUERY BUILDER
# ============================================================

def build_imap_search(env_config):
    # search_parts = ["ALL"]
    search_parts = ["UNSEEN"]
    
    ALLOWED_SENDERS = env_config['ALLOWED_SENDERS']
    ALLOWED_SUBJECT_KEYWORDS = env_config['ALLOWED_SUBJECT_KEYWORDS']
    SINCE_DATE = env_config['SINCE_DATE']
    

    if ALLOWED_SENDERS:
        if len(ALLOWED_SENDERS) == 1:
            search_parts.append(f'FROM "{ALLOWED_SENDERS[0]}"')
        else:
            s = f'OR FROM "{ALLOWED_SENDERS[0]}" FROM "{ALLOWED_SENDERS[1]}"'
            for sender in ALLOWED_SENDERS[2:]:
                s = f'OR {s} FROM "{sender}"'
            search_parts.append(s)

    if SINCE_DATE:
        imap_date = SINCE_DATE.strftime("%d-%b-%Y")
        search_parts.append(f"SINCE {imap_date}")

    if ALLOWED_SUBJECT_KEYWORDS:
        s = f'SUBJECT "{ALLOWED_SUBJECT_KEYWORDS[0]}"'
        for keyword in ALLOWED_SUBJECT_KEYWORDS[1:]:
            s = f'OR {s} SUBJECT "{keyword}"'
        search_parts.append(s)

    return " ".join(search_parts)

# ============================================================
# MAIN FETCH LOGIC
# ============================================================


def fetch_new_emails(env_id):
    imap = None
    saved_emails = []
    max_size_emails = []
    
    environment = Environment.objects.get(id=env_id)
    
    
    # Set environment config fields
    
    env_config = {
        "IMAP_EMAIL": environment.imap_email,
        "IMAP_PASSWORD": environment.get_imap_password(),
        "IMAP_HOST": environment.imap_host,
        "EMAIL_FOLDERS": list(environment.email_folders),
        "ALLOWED_FILE_TYPES": list(environment.allowed_file_types),
        "ALLOWED_SENDERS": list(environment.allowed_senders),
        "ALLOWED_SUBJECT_KEYWORDS": list(environment.allowed_subject_keywords),
        "BLOCKED_SUBJECT_KEYWORDS": list(environment.blocked_subject_keywords),
        "REQUIRE_ATTACHMENT": environment.require_attachment,
        "SINCE_DATE": datetime(environment.since_date.year, environment.since_date.month, environment.since_date.day)
    }
    
    print('ENV CONFIG:', env_config)

    try:
        imap = imap_login(env_config)
        
        # s, f = imap.list()
        # print('STATUS:', s)
        # print('FOLDERS:', f)

        # imap.select(env_config['EMAIL_FOLDERS'])

        for folder in env_config['EMAIL_FOLDERS']:
            logger.info(f"Selecting folder: {folder}")
            status, _ = imap.select(folder)
            print(f'SELECTING FOLDER ({folder}) STATUS:', status)
            
            if status != "OK":
                logger.warning(f"Failed to select folder '{folder}', skipping.")
                continue
                
            search_query = build_imap_search(env_config)
            logger.info(f"Running IMAP search in '{folder}' with: {search_query}")

            status, messages = imap.search(None, search_query)
            
            if status != "OK":
                logger.warning(f"Search failed in folder '{folder}'.")
                continue
                
            email_ids = messages[0].split()

            logger.info(f"Found {len(email_ids)} emails in '{folder}'.")

            for email_id in email_ids:
                try:
                    msg = fetch_email(imap, email_id)

                    # SUBJECT
                    raw_subject = msg.get("Subject", "")
                    decoded_parts = decode_header(raw_subject)
                    subject = "".join(
                        safe_decode(text) if isinstance(text, bytes) else text
                        for text, enc in decoded_parts
                    )

                    # Blocked keywords
                    if any(blk.lower() in subject.lower() for blk in env_config["BLOCKED_SUBJECT_KEYWORDS"]):
                        logger.info(f"Skipped — blocked subject: {subject}")
                        continue
                        
                    print('FETCHING EMAIL...', subject)
                    
                    message_id = msg.get("Message-ID")
                    
                    # Metadata
                    date_received = msg.get("Date")
                    date_parsed = parsedate_to_datetime(date_received) if date_received else datetime.now()
                    sender = msg.get("From", "")

                    # Extract content
                    body_text = ""
                    html_body = ""
                    attachments = []
                    has_attachment = False

                    total_file_size = 0
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            disp = str(part.get("Content-Disposition"))

                            if content_type == "text/plain" and "attachment" not in disp:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body_text += safe_decode(payload)

                            elif content_type == "text/html" and "attachment" not in disp:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    html_body += safe_decode(payload)

                            if "attachment" in disp:
                                has_attachment = True
                                filename = safe_decode(part.get_filename())
                                file_data = part.get_payload(decode=True)

                                if filename and file_data:
                                    # CRITICAL: If this fails → skip email
                                    saved, size = save_attachment(filename, file_data, env_config)
                                    if saved and size:
                                        attachments.append({
                                            "filename": filename,
                                            "file_path": saved,
                                            "file_size": size
                                        })
                                        print(f'SIZE OF {filename}:', format_bytes(size))
                                        total_file_size += size
                                        
                        print(f'TOTAL_FILE_SIZE FOR {subject}:',format_bytes(total_file_size)) 

                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            body_text = safe_decode(payload)

                    if env_config["REQUIRE_ATTACHMENT"] and not has_attachment:
                        logger.info(f"Skipped — attachment required: {subject}")
                        continue

                    if not body_text and html_body:
                        body_text = html_to_text(html_body)

                    max_size, status = False, 'pending'
                    if total_file_size > MAX_OPENAI_FILE_SIZE:
                        max_size, status = True, 'failed'
                        
                    
                    # ---------------------------------------------------------
                    # STEP 1: Create or get InternalEmail (global email object)
                    # ---------------------------------------------------------
                    try:
                        with transaction.atomic():
                            internal_email, created_internal = InternalEmail.objects.get_or_create(
                                message_id=message_id,
                                defaults={
                                    "subject": subject,
                                    "sender": sender,
                                    "body": body_text,
                                    "date_recieved": date_parsed,
                                    "attachments": attachments,
                                    "total_file_size": total_file_size
                                    # "message_id": message_id
                                }
                            )
                    except IntegrityError:
                        internal_email = InternalEmail.objects.get(message_id=message_id)

                    # ---------------------------------------------------------
                    # STEP 2: CHECK if EnvironmentEmail exists → skip immediately
                    # ---------------------------------------------------------
                    if EnvironmentEmail.objects.filter(environment=environment, internal_email=internal_email).exists():
                        # Already fetched for this environment — skip
                        continue

                    # ---------------------------------------------------------
                    # STEP 3: Create EnvironmentEmail safely
                    # ---------------------------------------------------------
                    try:
                        with transaction.atomic():
                            env_email, created_env_email = EnvironmentEmail.objects.get_or_create(
                                environment=environment,
                                internal_email=internal_email,
                                defaults={
                                    # "environment": environment,
                                    # "internal_email": internal_email,
                                    "status": status,
                                    # "max_size": max_size
                                }
                            )
                    except IntegrityError:
                        # Race condition: another request created it first
                        continue
                                    

                    if max_size: #50MB
                        max_size_emails.append(env_email)
                    else:
                        saved_emails.append(env_email)
                    logger.info(f"Saved email — {subject}")

                    # imap.store(email_id, '+FLAGS', '\\Seen')

                except CriticalRetryError as e:
                    logger.error(f"CRITICAL FAILURE — Skipping email {email_id}: {e}")
                    continue

                except RetryError as e:
                    logger.error(f"NON-CRITICAL FAILURE — Email saved anyway: {e}")
                    continue

                except Exception as e:
                    logger.error(f"Unexpected error processing {email_id}: {e}", exc_info=True)
                    continue

        logger.info("Completed email fetch.")

    finally:
        if imap:
            try:
                imap.close()
            except:
                pass
            imap.logout()

    return saved_emails, max_size_emails


from .ai_process import process_email  # the AI extraction function we wrote


def fetch_and_process_emails(env_id):
    """
    Fetch emails and automatically extract validated orders.
    Returns counts: (fetched, processed, failed)
    """
    fetched_emails, max_size_emails = fetch_new_emails(env_id)
    processed_count = 0
    failed_count = 0

    for env_email_obj in fetched_emails:
        try:
            if process_email(env_email_obj):
                processed_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error(f"AI processing failed for email {env_email_obj.id}: {e}", exc_info=True)
            failed_count += 1

    # return len(fetched_emails), len(max_size_emails), processed_count, failed_count
    model_instance_list_ids = [obj.id for obj in fetched_emails + max_size_emails]
    model_instance_list = EnvironmentEmail.objects.filter(id__in=model_instance_list_ids).order_by('-created_at')
    return model_instance_list