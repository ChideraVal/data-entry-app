import imaplib
import email
import os
import time
import logging
from functools import wraps
from email.header import decode_header
from email.utils import parsedate_to_datetime
from django.conf import settings
from ..models import IncomingOrderEmail
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import cloudinary.uploader

logger = logging.getLogger("email_monitor")

# -------------------
# CONFIGURATION
# -------------------

ALLOWED_FILE_TYPES = ["pdf", "png", "jpg", "jpeg", "webp", "txt"]

ALLOWED_SENDERS = ["fluxlite224@gmail.com"]
ALLOWED_SUBJECT_KEYWORDS = []
BLOCKED_SUBJECT_KEYWORDS = []
REQUIRE_ATTACHMENT = False

SINCE_DATE = datetime(2025, 12, 1)

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

# -------------------
# UTILITIES
# -------------------

def safe_decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value or ""

def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)

@retry(max_retries=3)
def save_attachment(filename, data):
    base, ext = os.path.splitext(filename)
    ext = ext[1:].lower()

    if ext not in ALLOWED_FILE_TYPES:
        logger.warning(f"Rejected attachment '{filename}' — unsupported file type.")
        return None

    counter = 1
    unique_filename = filename

    # Ensure no filename collision
    while default_storage.exists(f"emails/{unique_filename}"):
        unique_filename = f"{base}_{counter}.{ext}"
        counter += 1

    if settings.DEBUG:
        path = default_storage.save(f"emails/{unique_filename}", ContentFile(data))
        logger.info(f"Saved attachment '{filename}' → {path}")
        return path
    
    directory = "all_email_attachments"
    
    resource_type = 'image'
    
    if ext in ['pdf', 'txt']:
        resource_type = 'raw'
        
    res = cloudinary.uploader.upload(
        data,
        filename=unique_filename,   # IMPORTANT!
        folder=directory,
        resource_type=resource_type,
        use_filename=True
    )
    public_url = res.get("secure_url") or res.get("url")
    print('PUBLIC URL:', public_url)
    
    logger.info(f"Saved attachment '{filename}' → {public_url}")
    return public_url

# -------------------
# BUILD IMAP SEARCH QUERY
# -------------------

def build_imap_search():
    search_parts = ["ALL"]

    # Allowed senders
    if ALLOWED_SENDERS:
        if len(ALLOWED_SENDERS) == 1:
            search_parts.append(f'FROM "{ALLOWED_SENDERS[0]}"')
        else:
            s = f'OR FROM "{ALLOWED_SENDERS[0]}" FROM "{ALLOWED_SENDERS[1]}"'
            for sender in ALLOWED_SENDERS[2:]:
                s = f'OR {s} FROM "{sender}"'
            search_parts.append(s)

    # Since date
    if SINCE_DATE:
        imap_date = SINCE_DATE.strftime("%d-%b-%Y")
        search_parts.append(f"SINCE {imap_date}")

    # Allowed subject keywords
    if ALLOWED_SUBJECT_KEYWORDS:
        s = f'SUBJECT "{ALLOWED_SUBJECT_KEYWORDS[0]}"'
        for keyword in ALLOWED_SUBJECT_KEYWORDS[1:]:
            s = f'OR {s} SUBJECT "{keyword}"'
        search_parts.append(s)

    query = " ".join(search_parts)
    return query

# -------------------
# IMAP CONNECTION
# -------------------

@retry(max_retries=3)
def imap_login():
    imap = imaplib.IMAP4_SSL(settings.EMAIL_HOST_IMAP)
    imap.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
    imap.select(settings.EMAIL_FOLDER)
    logger.info("Successfully connected to IMAP server.")
    return imap

@retry(max_retries=2)
def fetch_email(imap, email_id):
    _, msg_data = imap.fetch(email_id, "(BODY.PEEK[])")
    return email.message_from_bytes(msg_data[0][1])

# -------------------
# MAIN FETCH FUNCTION
# -------------------

def fetch_new_emails():
    imap = None
    saved_emails = []

    try:
        imap = imap_login()

        search_query = build_imap_search()
        logger.info(f"Running IMAP search with: {search_query}")

        status, messages = imap.search(None, search_query)
        email_ids = messages[0].split()

        logger.info(f"Found {len(email_ids)} emails matching search criteria.")

        # processed = 0
        for email_id in email_ids:
            try:
                msg = fetch_email(imap, email_id)

                # Decode subject
                raw_subject = msg.get("Subject", "")
                decoded_parts = decode_header(raw_subject)
                subject = "".join(
                    safe_decode(text) if isinstance(text, bytes) else text
                    for text, enc in decoded_parts
                )
                
                # print('FETCHING EMAIL...', subject)

                # ---- Blocked keyword check ----
                if any(blk.lower() in subject.lower() for blk in BLOCKED_SUBJECT_KEYWORDS):
                    logger.info(f"Skipped — blocked subject: {subject}")
                    continue

                # ---- Duplicate check ----
                message_id = msg.get("Message-ID")
                if message_id and IncomingOrderEmail.objects.filter(message_id=message_id).exists():
                    # logger.info(f"Skipped duplicate email — Message-ID: {message_id}")
                    logger.info(f"Skipped — duplicate email: {subject}")
                    continue

                print('FETCHING EMAIL...', subject)

                # Parse metadata
                date_received = msg.get("Date")
                date_parsed = parsedate_to_datetime(date_received) if date_received else datetime.now()
                sender = msg.get("From", "")

                # Extract body and attachments
                body_text = ""
                html_body = ""

                attachments = []
                has_attachment = False

                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disp = str(part.get("Content-Disposition"))

                        # text/plain
                        if content_type == "text/plain" and "attachment" not in content_disp:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text += safe_decode(payload)

                        # text/html
                        elif content_type == "text/html" and "attachment" not in content_disp:
                            payload = part.get_payload(decode=True)
                            if payload:
                                html_body += safe_decode(payload)

                        # Attachments
                        if "attachment" in content_disp:
                            has_attachment = True
                            filename = safe_decode(part.get_filename())
                            file_data = part.get_payload(decode=True)
                            if filename and file_data:
                                saved = save_attachment(filename, file_data)
                                if saved:
                                    attachments.append({
                                        "filename": filename,
                                        "file_path": saved
                                    })

                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body_text = safe_decode(payload)

                # ---- Attachment required? ----
                if REQUIRE_ATTACHMENT and not has_attachment:
                    logger.info(f"Skipped — No attachment but required. Subject: {subject}")
                    continue

                # Fallback HTML → text
                if not body_text and html_body:
                    body_text = html_to_text(html_body)

                # Save email
                new_email = IncomingOrderEmail.objects.create(
                    subject=subject,
                    sender=sender,
                    body=body_text,
                    date_received=date_parsed,
                    attachments=attachments,
                    message_id=message_id
                )
                
                saved_emails.append(new_email)

                logger.info(f"Saved email from {sender} — '{subject}'")

                # Mark as read AFTER successful save
                imap.store(email_id, '+FLAGS', '\\Seen')
                
                # processed += 1
                            
            except Exception as e:
                logger.error(f"Error processing email {email_id}: {e}", exc_info=True)
                continue
            
        logger.info(f"Finished fetching emails. Processed {len(email_ids)} items.")
        # return processed
    finally:
        if imap:
            try:
                imap.close()
            except:
                pass
            imap.logout()
            logger.info("IMAP connection closed.")
    return saved_emails


from .ai_process import process_email  # the AI extraction function we wrote

def fetch_and_process_emails():
    """
    Fetch emails and automatically extract validated orders.
    Returns counts: (fetched, processed, failed)
    """
    fetched_emails = fetch_new_emails()
    processed_count = 0
    failed_count = 0

    for email_obj in fetched_emails:
        try:
            if process_email(email_obj):
                processed_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error(f"AI processing failed for email {email_obj.id}: {e}", exc_info=True)
            failed_count += 1

    return len(fetched_emails), processed_count, failed_count
