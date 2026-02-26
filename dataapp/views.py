from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.dateformat import format as dj_format
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, update_session_auth_hash
from .utils.email_monitor import fetch_and_process_emails, save_attachment, format_bytes, MAX_OPENAI_FILE_SIZE
from .utils.ai_process import process_email, process_upload
from .forms import SchemaForm, EnvironmentForm
from django.forms import ValidationError
from .models import Environment, EnvironmentEmail, EnvironmentUpload, ExtractionResult, Schema, AuditLog
import json
import csv
from .utils.table import *
from django.views.decorators.http import require_POST
import random
from .forms import *
from django.contrib.auth.forms import PasswordChangeForm
from .permissions import Roles, ViewType, require_roles, block_roles
from django.core.paginator import Paginator
from django.db.models import Q, F, Func, Value, CharField
from django.core.cache import cache
from django.conf import settings
from datetime import datetime, timedelta
from django.utils import timezone
import csv
from datetime import datetime, timedelta
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.db.models import Q
import csv
import json
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404


class Echo:
    """
    An object that implements just the write method of the file-like
    interface. Used by csv.writer to stream rows one by one.
    """
    
    def write(self, value):
        return value

# Tune this threshold according to your environment. If log rows exceed this number,
# backend filtering/search will be used. Below is a sensible default.
AUDIT_LOG_BACKEND_FILTER_THRESHOLD = getattr(settings, "AUDIT_LOG_BACKEND_FILTER_THRESHOLD", 0) # All search and filter done on the backend

# cache key and ttl for available filters
_CACHE_ENABLED = True
_AVAILABLE_FILTERS_CACHE_KEY = "audit_log_available_filters_v1"
_AVAILABLE_FILTERS_TTL = getattr(settings, "AUDIT_LOG_AVAILABLE_FILTERS_TTL", 60 * 10)  # 10 minutes



def not_found(request, exception):
    return render(request, '404.html')

def permission_denied(request, exception):
    return render(request, '403.html')

def server_error(request):
    return render(request, '500.html')


def sign_in(request):
    path = request.get_full_path()
    next_url = path.replace('/signin/?next=', '')
    if request.method == 'POST':
        form = CustomAuthForm(request, request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if next_url == '/signin/' or next_url == '/signup/':
                return redirect('dashboard')
            return redirect(next_url)    
        else:
            print(form.errors)
            return render(request, 'signin.html', {'form': form})
    form = CustomAuthForm(request)
    return render(request, 'signin.html', {'form': form})

def sign_up(request):
    path = request.get_full_path()
    next_url = path.replace('/signup/?next=', '')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            print('NEXT URL POST: ', next_url)
            if next_url == '/signin/' or next_url == '/signup/':
                return redirect('dashboard')
            return redirect(next_url)
        else:
            print(form.errors)
            return render(request, 'signup.html', {'form': form})
    print('NEXT URL GET: ', next_url)
    form = CustomUserCreationForm()
    return render(request, 'signup.html', {'form': form})

@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect('profile')
        else:
            print(form.errors)
            return render(request, 'change_password.html', {'form': form})
    form = PasswordChangeForm(user=request.user)
    return render(request, 'change_password.html', {'form': form})

@login_required
def sign_out(request):
    logout(request)
    return redirect('signin')

@login_required
def dashboard(request):
    environments = Environment.objects.all()
    return render(request, 'list_env.html', {'environments': environments})

@login_required
def list_schemas(request):
    schemas = Schema.objects.all()
    return render(request, 'list_schemas.html', {'schemas': schemas})

@login_required
def profile(request):
    return render(request, 'profile.html')

@login_required
def view_environment_emails(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    return render(request, 'view_env_emails.html', {'env_id': environment.pk, 'environment': environment})

@login_required
def view_environment_files(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    return render(request, 'view_env_files.html', {'env_id': environment.pk, 'environment': environment})

@login_required
def review_email_result(request, email_id):
    environment_email = get_object_or_404(EnvironmentEmail, id=email_id)
    result = environment_email.result
    file_urls = ""
    for file in environment_email.internal_email.attachments:
        file_path = file['file_path']
        file_urls += file_path + "\n"
    print('FILE URLS:', file_urls)
    return render(request, 'result_review.html', {
        'result': result,
        "schema_json": json.dumps(result.environment.schema.schema_json),
        "file_urls": file_urls})

@login_required
def review_upload_result(request, upload_id):
    environment_upload = get_object_or_404(EnvironmentUpload, id=upload_id)
    result = environment_upload.result
    file_urls = ""
    for file in environment_upload.attachments:
        file_path = file['file_path']
        file_urls += file_path + "\n"
    print('FILE URLS:', file_urls)
    print('SCHEMA JSON: ', json.dumps(result.environment.schema.schema_json))
    return render(request, 'result_review.html', {
        'result': result,
        "schema_json": json.dumps(result.environment.schema.schema_json),
        "file_urls": file_urls})

@login_required
@require_POST
def save_email_result(request, email_id):
    print('SAVING JSON...')
    payload = json.loads(request.body)

    data = payload.get("data")
    approve = payload.get("approve", False)

    environment_email = get_object_or_404(EnvironmentEmail, id=email_id)
    result = environment_email.result


    result.raw_json = json.dumps(data)

    if approve:
        result.is_approved = True
    else:
        result.is_approved = False

    result.save()

    return JsonResponse({
        "ok": True,
        "status": result.is_approved
    })

@login_required
@require_POST
def save_upload_result(request, upload_id):
    print('SAVING JSON...')
    payload = json.loads(request.body)

    data = payload.get("data")
    approve = payload.get("approve", False)

    environment_upload = get_object_or_404(EnvironmentUpload, id=upload_id)
    result = environment_upload.result


    result.raw_json = json.dumps(data)

    if approve:
        result.is_approved = True
    else:
        result.is_approved = False

    result.save()

    return JsonResponse({
        "ok": True,
        "status": result.is_approved
    })

@login_required
def delete_email_result(request, email_id):
    print('DELETING EMAIL DATA...')

    environment_email = get_object_or_404(EnvironmentEmail, id=email_id)
    result = environment_email.result

    result.delete()

    environment_email.status = "failed"

    environment_email.save()

    return redirect("environment_emails_view", environment_email.environment.id)

@login_required
def delete_upload_result(request, upload_id):
    print('DELETING UPLOAD DATA...')

    environment_upload = get_object_or_404(EnvironmentUpload, id=upload_id)
    result = environment_upload.result

    result.delete()

    environment_upload.status = "failed"

    environment_upload.save()

    return redirect("environment_files_view", environment_upload.environment.id)

@login_required
def get_extracted_data_row_sources(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    
    emails = (
        EnvironmentEmail.objects
        .filter(environment=environment, result__raw_json__isnull=False)
        .only("result__raw_json")
    )
    
    uploads = (
        EnvironmentUpload.objects
        .filter(environment=environment, result__raw_json__isnull=False)
        .only("result__raw_json")
    )

    discovered_paths = set()

    for email in list(emails) + list(uploads):
        data = json.loads(email.result.raw_json)
        # print('DATA:', data)
        print(type(data))
        if not isinstance(data, dict):
            continue

        paths = discover_array_paths(data)
        print('PATHS:', paths)
        discovered_paths.update(paths)
        print('DISCOVERED PATHS:', discovered_paths)

    sources = [{
        "key": "document",
        "label": "Document (1 row per email)"
    }]

    for path in sorted(discovered_paths):
        sources.append({
            "key": path,
            "label": f"{path} (array of objects)"
        })
    
    print(sources)

    return JsonResponse({
        "default": "document",
        "sources": sources
    })

@login_required
def view_extracted_data(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    return render(request, "data_view.html", {
        "environment": environment
    })

@login_required
def get_extracted_data(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)

    # 1️⃣ Read UI params
    approval_mode = request.GET.get("approval", "all")
    row_source = request.GET.get("row_source")  # None or "orders"
    max_depth = int(request.GET.get("depth", 2))
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 50))
    
    page = max(1, page)
    page_size = max(1, page_size)



    # columns=user_id,supplier.name,order_id
    visible_columns = request.GET.get("columns")
    if visible_columns:
        visible_columns = visible_columns.split(",")
    else:
        visible_columns = None

    # 2️⃣ Fetch emails
    emails = (
        EnvironmentEmail.objects
        .filter(environment=environment, status="successful")
        .only("internal_email__id", "result__is_approved", "result__raw_json")
    )
    
    uploads = (
        EnvironmentUpload.objects
        .filter(environment=environment, status="successful")
        .only("id", "result__is_approved", "result__raw_json")
    )
    
    
    # 3️⃣ Convert ORM → plain records
    records = [
        {
            "email_id": email.id,
            "status": email.result.is_approved,
            "document": json.loads(email.result.raw_json)
        }
        for email in (list(emails) + list(uploads))
    ]

    # 4️⃣ Approval filter (UI)
    f_records = filter_records_by_approval(records, mode=approval_mode)

    # 5️⃣ Row extraction
    rows = []
    for r in records:
        rows.extend(
            build_rows_from_document(
                r["document"],
                row_source=row_source
            )
        )
    
    f_rows = []
    for r in f_records:
        f_rows.extend(
            build_rows_from_document(
                r["document"],
                row_source=row_source
            )
        )

    # 6️⃣ Schema discovery
    all_columns = discover_schema(rows, max_depth=max_depth)

    # 7️⃣ Column visibility
    if visible_columns is not None:
        print("IT'S NOT NONE")
        columns = apply_column_visibility(all_columns, visible_columns)
    else:
        columns = all_columns

    print("ALL COLUMNS:", all_columns)
    print("VISIBLE COLUMNS:", columns)

    # 8️⃣ Projection
    table = project_rows(f_rows, columns, max_depth=max_depth)

    # 9️⃣ Pagination
    page_rows, total_rows = paginate_table(table, page=page, page_size=page_size)

    return JsonResponse({
        "all_columns": all_columns,
        "columns": columns,
        "rows": page_rows,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "approval_mode": approval_mode,
            "row_source": row_source
        }
    })

# @login_required
# def export_extracted_data(request, env_id):
#     """
#     Export all approved extracted data as CSV.

#     ✅ Ignores any pagination
#     ✅ Applies approval filter
#     ✅ Applies row source selection
#     ✅ Applies column visibility
#     """
#     environment = get_object_or_404(Environment, id=env_id)

#     # --- Read user config ---
#     row_source = request.GET.get("row_source")  # None or array path
#     max_depth = int(request.GET.get("depth", 2))

#     visible_columns = request.GET.get("columns")
#     if visible_columns:
#         visible_columns = visible_columns.split(",")

#     # --- Fetch emails for this environment ---
#     emails = (
#         EnvironmentEmail.objects
#         .filter(environment=environment, status="successful")
#         .only("internal_email__id", "result__is_approved", "result__raw_json")
#     )
    
#     uploads = (
#         EnvironmentUpload.objects
#         .filter(environment=environment, status="successful")
#         .only("id", "result__is_approved", "result__raw_json")
#     )
    
#     records = [
#         {
#             "email_id": email.id,
#             "status": email.result.is_approved,
#             "document": json.loads(email.result.raw_json)
#         }
#         for email in list(emails) + list(uploads)
#     ]

#     # --- Enforce export policy (only approved emails) ---
#     f_records = enforce_export_policy(records)

#     # --- Row extraction ---
#     rows = []
#     for r in records:
#         rows.extend(
#             build_rows_from_document(
#                 r["document"],
#                 row_source=row_source
#             )
#         )
    
#     f_rows = []
#     for r in f_records:
#         f_rows.extend(
#             build_rows_from_document(
#                 r["document"],
#                 row_source=row_source
#             )
#         )

#     # --- Schema discovery ---
#     all_columns = discover_schema(rows, max_depth=max_depth)

#     # --- Apply column visibility ---
#     if visible_columns:
#         columns = apply_column_visibility(all_columns, visible_columns)
#     else:
#         columns = all_columns

#     table = project_rows(f_rows, columns, max_depth=max_depth)
#     print('TABLE:', table)

#     # --- CSV response ---
#     response = HttpResponse(content_type="text/csv")
#     response["Content-Disposition"] = "attachment; filename=extracted_data.csv"

#     writer = csv.DictWriter(response, fieldnames=columns)
#     writer.writeheader()
#     for row in table:
#         writer.writerow(row)

#     return response

def export_extracted_data(request, env_id):
    """
    Fully streaming CSV export with lazy schema discovery.

    ✅ Ignores pagination
    ✅ Applies approval filter
    ✅ Applies row source selection
    ✅ Applies column visibility
    ✅ Minimal memory usage (constant memory)
    """

    environment = get_object_or_404(Environment, id=env_id)

    # --- User config ---
    row_source = request.GET.get("row_source")  # None or array path
    max_depth = int(request.GET.get("depth", 2))
    visible_columns = request.GET.get("columns")
    if visible_columns:
        visible_columns = visible_columns.split(",")

    # --- Fetch emails and uploads ---
    emails = (
        EnvironmentEmail.objects
        .filter(environment=environment, status="successful")
        .only("internal_email__id", "result__is_approved", "result__raw_json")
    )
    uploads = (
        EnvironmentUpload.objects
        .filter(environment=environment, status="successful")
        .only("id", "result__is_approved", "result__raw_json")
    )

    all_records_qs = list(emails.iterator()) + list(uploads.iterator())

    # --- Parse JSON and enforce export policy ---
    records = []
    for r in all_records_qs:
        try:
            doc = json.loads(r.result.raw_json)
        except Exception:
            continue
        records.append({
            "id": getattr(r, "id", None),
            "status": r.result.is_approved,
            "document": doc
        })

    f_records = enforce_export_policy(records)  # approved only

    # --- Lazy schema discovery ---
    def iter_rows_for_schema():
        for r in records:
            yield from build_rows_from_document(r["document"], row_source=row_source)

    all_columns = discover_schema(iter_rows_for_schema(), max_depth=max_depth)

    # --- Column visibility ---
    if visible_columns:
        columns = apply_column_visibility(all_columns, visible_columns)
    else:
        columns = all_columns

    columns_upper = [c.upper() for c in columns] # convert columns to upper case
    # --- Streaming row generator ---
    def row_generator():
        pseudo_buffer = Echo()
        writer = csv.DictWriter(pseudo_buffer, fieldnames=columns_upper) # use "columns" later if needed

        # Write header
        yield writer.writeheader()

        # Lazily generate rows per approved record
        for r in f_records:
            rows_iter = build_rows_from_document(r["document"], row_source=row_source)
            projected_rows = project_rows(rows_iter, columns, max_depth=max_depth)
            for row in projected_rows:
                row_upper = {k.upper(): v for k, v in row.items()} # convert row keys to upper case
                yield writer.writerow(row_upper) # use "row" later if needed

    # --- Return streaming response ---
    response = StreamingHttpResponse(
        row_generator(),
        content_type="text/csv"
    )
    response["Content-Disposition"] = "attachment; filename=extracted_data.csv"
    return response


# --- Helper: optimized serializer ------------------------------------------------
def serialize_emails(qs):
    """
    Convert a queryset (or list of dicts from values()) into a JSON-serializable list
    with compact fields. Uses QuerySet.values() before calling this for best performance.
    Output fields match the UI expectations:
      id, subject, from, date, status, sizeKb
    """
    # If qs is a QuerySet, use values() to reduce DB load
    if hasattr(qs, "values"):
        items = list(qs.values(
            "id",
            "internal_email__subject",
            "internal_email__sender",
            "internal_email__attachments",
            "internal_email__date_recieved",
            "status",
            "internal_email__total_file_size",
            "result__is_approved"
        ))
    else:
        # assume it's already a list/dict
        items = list(qs)

    print('ITEMS:', items)
    out = []
    for it in items:
        # format date safely
        dt = it.get("internal_email__date_recieved")
        if dt is None:
            date_str = None
        else:
            # Use ISO-like short format, e.g. "2025-12-09 14:23"
            try:
                # date_str = dj_format(dt, "Y-m-d H:i")
                date_str = timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                date_str = str(dt)

        out.append({
            "id": it.get("id"),
            "subject": it.get("internal_email__subject"),
            "from": it.get("internal_email__sender") or "",
            "date": date_str,
            "status": it.get("status"),
            "attachments": it.get("internal_email__attachments"),
            "total_file_size": it.get("internal_email__total_file_size"),
            "is_approved": it.get("result__is_approved")
        })
    return out

# --- Utility: compute simple metrics and summary --------------------------------
def compute_email_metrics_and_summary(environment):
    """
    Minimal, read-only metrics derived directly from DB counts.
    Returns: (metrics_dict, summary_dict)
    """
        
    counts = {
        "pending": environment.environment_emails.filter(status="pending").count(),
        "failed":  environment.environment_emails.filter(status="failed").count(),
        "success": environment.environment_emails.filter(status="successful").count(),
    }

    summary = {
        "pending": counts.get("pending") or 0,
        "failed": counts.get("failed") or 0,
        "successful": counts.get("success") or 0,
    }
    
    total_emails = environment.environment_emails.count()  # example doc count
    total_approved_extraction_results = environment.results.filter(environment_email__isnull=False ,is_approved=True).count()  # example doc count
    total_extraction_results = environment.results.filter(environment_email__isnull=False).count()  # example doc count
    
    # For "documents processed this month" you probably have a different query;
    # this is a placeholder that uses total as the 'value' and total+100 as limit.
    metrics = {
        "docs": {"value": 3, "limit": max(500, 200)},
        "emails": {"value": counts.get("success") or 0, "limit": total_emails},
        "orders": {"value": total_approved_extraction_results, "limit": total_extraction_results},
    }
    return metrics, summary

# --- Views -----------------------------------------------------------------------
@login_required
@require_http_methods(["GET", "POST"])
def scan_inbox(request, env_id):
    """
    Endpoint: /api/scan-inbox/
    Purpose: return a list of newly-scanned (most recent) emails + metrics + summary.
    Note: no 'scanning' logic is performed here (per your instruction). We simply return
    the most recent N emails from the Email model to act as the 'scanned' results.
    """
    environment = get_object_or_404(Environment, pk=env_id)
        
    # choose how many "new" emails to return; adjust as you like
    fetched_emails = fetch_and_process_emails(env_id)
    emails = serialize_emails(fetched_emails)

    metrics, summary = compute_email_metrics_and_summary(environment)
    payload = {
        "emails": emails,
        "metrics": metrics,
        "summary": summary,
    }
    return JsonResponse(payload, status=200)

@login_required
@require_http_methods(["GET"])
def list_emails(request, env_id):
    print('ENV ID:',env_id)
    environment = get_object_or_404(Environment, pk=env_id)
    print('LISTING EMAILS...')
    """
    Endpoint: /api/emails/
    Returns the full list of emails (or optionally filtered by status/search via query params).
    This is a simple read-only listing that returns JSON-converted email objects.
    """
    recent_qs = environment.environment_emails.order_by("-created_at")
    
    emails = serialize_emails(recent_qs)
    print('ENV EMAILS:', emails)

    metrics, summary = compute_email_metrics_and_summary(environment)
    payload = {
        "emails": emails,
        "metrics": metrics,
        "summary": summary,
    }
    return JsonResponse(payload, status=200)

# @require_http_methods(["GET"])
# def list_emails(request):
#     """
#     Endpoint: /api/emails/
#     Returns the full list of emails (or optionally filtered by status/search via query params).
#     This is a simple read-only listing that returns JSON-converted email objects.
#     """
#     qs = Email.objects.all().order_by("-date")

#     # basic status filter
#     status = request.GET.get("status")
#     if status in ("pending", "failed", "success"):
#         qs = qs.filter(status=status)

#     # optional search on subject/from
#     q = request.GET.get("q")
#     if q:
#         qs = qs.filter(subject__icontains=q) | qs.filter(from_email__icontains=q)

#     emails = serialize_emails(qs)
#     return JsonResponse({"emails": emails}, status=200)

@login_required
@require_http_methods(["POST"])
def reprocess_email(request, email_id):
    """
    Endpoint: /api/emails/<email_id>/reprocess/
    Minimal behavior: return a JSON object with a 'processed' boolean and the email object.
    No processing logic is implemented; we simply fetch the email and return it.
    """
    try:
        email = EnvironmentEmail.objects.filter(pk=email_id)
    except EnvironmentEmail.DoesNotExist:
        return JsonResponse({"processed": False, "error": "not_found"}, status=404)

    processed = process_email(email.first())
    
    environment = email.first().environment
    
    email_dict = serialize_emails(email)[0]

    metrics, summary = compute_email_metrics_and_summary(environment)
    # Since no logic is to be executed here, we do not change email.status.
    # We still return a 'processed' key; caller/backend can decide what that means.
    return JsonResponse({
        "processed": processed,
        "email": email_dict,
        "metrics": metrics,
        "summary": summary
    }, status=200)


@login_required
@require_http_methods(["POST"])
def reprocess_all_failed(request, env_id):
    """
    Endpoint: /api/reprocess-failed/
    Returns a JSON list of { processed: bool, email: {...} } for all emails where status == 'failed'.
    No reprocessing is performed here; this view only returns the data structure for the client.
    """
    
    environment = get_object_or_404(Environment, pk=env_id)
    
    # failed_qs = environment.environment_emails.filter(status="failed").order_by("-created_at")
    failed_qs = environment.environment_emails.filter(status="failed")
    print('FAILED QS:', failed_qs)
    
    for email in failed_qs:
        process_email(email)

    # failed_emails = serialize_emails(failed_qs)
    failed_emails_ids = [obj.id for obj in failed_qs]
    failed_emails = serialize_emails(EnvironmentEmail.objects.filter(id__in=failed_emails_ids))


    # Build results list; since there's no processing logic, mark processed as False by default.
    results = [{"processed": True, "email": e} for e in failed_emails]
    print('RESULTS:', results)

    metrics, summary = compute_email_metrics_and_summary(environment)
    return JsonResponse({
        "results": results,
        "metrics": metrics,
        "summary": summary
    }, status=200)


@login_required
@require_http_methods(["DELETE", "POST"])
def delete_email(request, email_id):
    """
    Endpoint: /api/emails/<email_id>/delete/
    Minimal delete endpoint. Performs the delete and returns deletion status.
    (This one performs a single-line DB action; it's intentionally minimal.)
    """
    
    environment_email = get_object_or_404(EnvironmentEmail, pk=email_id)
    environment = environment_email.environment
    deleted, _ = environment_email.delete()
    
    if deleted:
        metrics, summary = compute_email_metrics_and_summary(environment)
        return JsonResponse({"deleted": True, "id": email_id, "metrics": metrics}, status=200)
    return JsonResponse({"deleted": False, "id": email_id}, status=404)






# -----------------------------------------------
# ENVIRONMENT UPLOAD VIEWS
# -----------------------------------------------

# --- Helper: optimized serializer ------------------------------------------------
def serialize_uploads(qs):
    """
    Convert a queryset (or list of dicts from values()) into a JSON-serializable list
    with compact fields. Uses QuerySet.values() before calling this for best performance.
    Output fields match the UI expectations:
      id, subject, from, date, status, sizeKb
    """
    # If qs is a QuerySet, use values() to reduce DB load
    if hasattr(qs, "values"):
        items = list(qs.values(
            "id",
            "name",
            "status",
            "created_at",
            "attachments",
            "total_file_size",
            "result__is_approved"
        ))
    else:
        # assume it's already a list/dict
        items = list(qs)

    print('ITEMS:', items)
    out = []
    for it in items:
        # format date safely
        dt = it.get("created_at")
        if dt is None:
            date_str = None
        else:
            # Use ISO-like short format, e.g. "2025-12-09 14:23"
            try:
                # date_str = dj_format(dt, "Y-m-d H:i")
                date_str = timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                date_str = str(dt)

        out.append({
            "id": it.get("id"),
            "name": it.get("name"),
            "date": date_str,
            "status": it.get("status"),
            "attachments": it.get("attachments"),
            "total_file_size": it.get("total_file_size"),
            "is_approved": it.get("result__is_approved")
        })
    return out

# --- Utility: compute simple metrics and summary --------------------------------
def compute_file_metrics_and_summary(environment):
    """
    Minimal, read-only metrics derived directly from DB counts.
    Returns: (metrics_dict, summary_dict)
    """
        
    counts = {
        "pending": environment.environment_uploads.filter(status="pending").count(),
        "failed":  environment.environment_uploads.filter(status="failed").count(),
        "success": environment.environment_uploads.filter(status="successful").count(),
    }

    summary = {
        "pending": counts.get("pending") or 0,
        "failed": counts.get("failed") or 0,
        "successful": counts.get("success") or 0,
    }
    
    total_uploads = environment.environment_uploads.count()  # example doc count
    total_approved_extraction_results = environment.results.filter(environment_upload__isnull=False, is_approved=True).count()  # example doc count
    total_extraction_results = environment.results.filter(environment_upload__isnull=False).count()  # example doc count
    
    # For "documents processed this month" you probably have a different query;
    # this is a placeholder that uses total as the 'value' and total+100 as limit.
    metrics = {
        "docs": {"value": 3, "limit": max(500, 200)},
        "emails": {"value": counts.get("success") or 0, "limit": total_uploads},
        "orders": {"value": total_approved_extraction_results, "limit": total_extraction_results},
    }
    return metrics, summary

# --- Views -----------------------------------------------------------------------
@login_required
@require_POST
def upload_files(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    files = request.FILES.getlist('files')
    
    print('FILES:', files)
    attachments = []
    
    env_config = {
        "ALLOWED_FILE_TYPES": list(environment.allowed_file_types)
    }
    
    total_file_size = 0
    for f in files:
        saved, size = save_attachment(f.name, f.read(), env_config)
        if saved and size:
            attachments.append({
                "filename": f.name,
                "file_path": saved,
                "file_size": size
            })
            print(f'SIZE OF {f.name}:', format_bytes(size))
            total_file_size += size
            
    print('TOTAL FILE SIZE:', format_bytes(total_file_size))
    
    max_size, status = False, 'pending'
    if total_file_size > MAX_OPENAI_FILE_SIZE:
        max_size, status = True, 'failed'

    if len(attachments) > 0:
        env_upload = EnvironmentUpload.objects.create(
            environment=environment,
            name=f"New Upload",
            status=status,
            attachments=attachments,
            total_file_size=total_file_size
        )
        
        env_upload.name = f"Upload #{env_upload.id}"
        env_upload.save()
        
        if not max_size:
            process_upload(env_upload)
            
        uploads = EnvironmentUpload.objects.filter(environment=environment, pk=env_upload.pk)
        uploads = serialize_uploads(uploads)
    else:
        uploads = []


    metrics, summary = compute_file_metrics_and_summary(environment)
    
    
    payload = {
        "uploads": uploads,
        "metrics": metrics,
        "summary": summary,
    }
    return JsonResponse(payload, status=200)

@login_required
@require_http_methods(["GET"])
def list_uploads(request, env_id):
    print('ENV ID:',env_id)
    environment = get_object_or_404(Environment, pk=env_id)
    print('LISTING UPLOADS...')
    """
    Endpoint: /api/emails/
    Returns the full list of emails (or optionally filtered by status/search via query params).
    This is a simple read-only listing that returns JSON-converted email objects.
    """
    recent_qs = environment.environment_uploads.order_by("-created_at")
    
    uploads = serialize_uploads(recent_qs)
    print('ENV UPLOADS:', uploads)

    metrics, summary = compute_file_metrics_and_summary(environment)
    payload = {
        "uploads": uploads,
        "metrics": metrics,
        "summary": summary,
    }
    return JsonResponse(payload, status=200)

@login_required
@require_http_methods(["POST"])
def reprocess_upload(request, upload_id):
    """
    Endpoint: /api/emails/<email_id>/reprocess/
    Minimal behavior: return a JSON object with a 'processed' boolean and the email object.
    No processing logic is implemented; we simply fetch the email and return it.
    """
    try:
        upload = EnvironmentUpload.objects.filter(pk=upload_id)
    except EnvironmentUpload.DoesNotExist:
        return JsonResponse({"processed": False, "error": "not_found"}, status=404)

    processed = process_upload(upload.first())
    
    environment = upload.first().environment
    
    upload_dict = serialize_uploads(upload)[0]

    metrics, summary = compute_file_metrics_and_summary(environment)
    # Since no logic is to be executed here, we do not change email.status.
    # We still return a 'processed' key; caller/backend can decide what that means.
    return JsonResponse({
        "processed": processed,
        "upload": upload_dict,
        "metrics": metrics,
        "summary": summary
    }, status=200)


@login_required
@require_http_methods(["POST"])
def reprocess_all_failed_uploads(request, env_id):
    """
    Endpoint: /api/reprocess-failed/
    Returns a JSON list of { processed: bool, email: {...} } for all emails where status == 'failed'.
    No reprocessing is performed here; this view only returns the data structure for the client.
    """
    
    environment = get_object_or_404(Environment, pk=env_id)
    
    # failed_qs = environment.environment_emails.filter(status="failed").order_by("-created_at")
    failed_qs = environment.environment_uploads.filter(status="failed")
    print('FAILED QS:', failed_qs)
    
    for upload in failed_qs:
        process_upload(upload)

    # failed_emails = serialize_emails(failed_qs)
    failed_uploads_ids = [obj.id for obj in failed_qs]
    failed_uploads = serialize_uploads(EnvironmentUpload.objects.filter(id__in=failed_uploads_ids))


    # Build results list; since there's no processing logic, mark processed as False by default.
    results = [{"processed": True, "upload": u} for u in failed_uploads]
    print('RESULTS:', results)

    metrics, summary = compute_file_metrics_and_summary(environment)
    return JsonResponse({
        "results": results,
        "metrics": metrics,
        "summary": summary
    }, status=200)

@login_required
@require_http_methods(["DELETE", "POST"])
def delete_upload(request, upload_id):
    """
    Endpoint: /api/emails/<email_id>/delete/
    Minimal delete endpoint. Performs the delete and returns deletion status.
    (This one performs a single-line DB action; it's intentionally minimal.)
    """
    print('DELETING...')
    environment_upload = get_object_or_404(EnvironmentUpload, pk=upload_id)
    environment = environment_upload.environment
    deleted, _ = environment_upload.delete()
    
    if deleted:
        metrics, summary = compute_file_metrics_and_summary(environment)
        return JsonResponse({"deleted": True,"id": upload_id, "metrics": metrics}, status=200)
    return JsonResponse({"deleted": False, "id": upload_id}, status=404)

@login_required
@require_http_methods(["POST"])
def rename_upload(request, upload_id):
    """
    Endpoint: /api/emails/<email_id>/delete/
    Minimal delete endpoint. Performs the delete and returns deletion status.
    (This one performs a single-line DB action; it's intentionally minimal.)
    """
    print('RENAMING...')
    
    try:
        upload = EnvironmentUpload.objects.filter(pk=upload_id)
    except EnvironmentUpload.DoesNotExist:
        return JsonResponse({"renamed": False, "error": "not_found"}, status=404)

    environment_upload = upload.first()
    environment = environment_upload.environment
    
    payload = json.loads(request.body)
    
    print("PAYLOAD: ", payload)

    name = payload.get("name", False)
    
    if name and not EnvironmentUpload.objects.filter(name__iexact=name, environment=environment).exists():
        print('NO EXISTING NAME')
        environment_upload.name = name
        environment_upload.save()
    
    upload_dict = serialize_uploads(upload)[0]
    
    # if name and not EnvironmentUpload.objects.filter(name__iexact=name, environment=environment).exists():
    metrics, summary = compute_file_metrics_and_summary(environment)
    return JsonResponse({"renamed": True, "upload": upload_dict, "metrics": metrics}, status=200)
    # return JsonResponse({"renamed": False}, status=404)

# -----------------------------------------------
# USER VIEWS
# -----------------------------------------------

# --- Helper: optimized serializer ------------------------------------------------
def serialize_users(qs):
    """
    Convert a queryset (or list of dicts from values()) into a JSON-serializable list
    with compact fields. Uses QuerySet.values() before calling this for best performance.
    Output fields match the UI expectations:
      id, subject, from, date, status, sizeKb
    """
    # If qs is a QuerySet, use values() to reduce DB load
    if hasattr(qs, "values"):
        items = list(qs.values(
            "id",
            "username",
            "role",
            "is_active",
            "date_joined",
            "last_login"
        ))
    else:
        # assume it's already a list/dict
        items = list(qs)

    print('ITEMS:', items)
    out = []
    for it in items:
        # format date safely
        dt = it.get("date_joined")
        dt2 = it.get("last_login")
        if dt is None:
            date_str = None
        else:
            # Use ISO-like short format, e.g. "2025-12-09 14:23"
            try:
                # date_str = dj_format(dt, "Y-m-d H:i")
                date_str = timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                date_str = str(dt)

        if dt2 is None:
            date_str2 = None
        else:
            # Use ISO-like short format, e.g. "2025-12-09 14:23"
            try:
                # date_str = dj_format(dt, "Y-m-d H:i")
                date_str2 = timezone.localtime(dt2).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                date_str2 = str(dt2)

        out.append({
            "id": it.get("id"),
            "username": it.get("username"),
            "date_joined": date_str,
            "last_login": date_str2,
            "role": it.get("role"),
            "is_active": it.get("is_active")
        })
    print("SERIALIZED: ", out)
    return out

# --- Views -----------------------------------------------------------------------
@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.JSON)
@require_http_methods(["GET"])
def list_users(request):
    print('LISTING USERS...')
    """
    Endpoint: /api/emails/
    Returns the full list of emails (or optionally filtered by status/search via query params).
    This is a simple read-only listing that returns JSON-converted email objects.
    """
    
    # if request.user.is_member():
    #     return JsonResponse({"users": []}, status=200)
    
    if request.user.is_super_admin():
        recent_qs = User.objects.exclude(id=request.user.pk).exclude(role="super admin").order_by("-date_joined")
    if request.user.is_admin():
        recent_qs = User.objects.exclude(id=request.user.pk).filter(role="member").order_by("-date_joined")
    
    users = serialize_users(recent_qs)
    print('USERS:', users)

    # metrics, summary = compute_email_metrics_and_summary(environment)
    
    # total_active_users = User.objects.filter(is_active=True).count()
    
    payload = {
        "users": users,
        # "metrics": {
        #     "active_users": {
        #         "value": total_active_users,
        #         "limit": 5000
        #     }
        # }
        # "summary": summary,
    }
    return JsonResponse(payload, status=200)

@login_required
@require_http_methods(["DELETE", "POST"])
def delete_user(request, upload_id):
    """
    Endpoint: /api/emails/<email_id>/delete/
    Minimal delete endpoint. Performs the delete and returns deletion status.
    (This one performs a single-line DB action; it's intentionally minimal.)
    """
    print('DELETING...')
    environment_upload = get_object_or_404(EnvironmentUpload, pk=upload_id)
    environment = environment_upload.environment
    deleted, _ = environment_upload.delete()
    
    if deleted:
        metrics, summary = compute_email_metrics_and_summary(environment)
        return JsonResponse({"deleted": True,"id": upload_id, "metrics": metrics}, status=200)
    return JsonResponse({"deleted": False, "id": upload_id}, status=404)


@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.JSON)
@require_http_methods(["POST"])
def add_user(request):
    """
    Endpoint: /api/emails/<email_id>/delete/
    Minimal delete endpoint. Performs the delete and returns deletion status.
    (This one performs a single-line DB action; it's intentionally minimal.)
    """
    print('ADDING...')
    
    # try:
    #     user_qs =  User.objects.filter(pk=user_id)
    #     print('FOUND USER: ', user_qs)
    # except User.DoesNotExist:
    #     return JsonResponse({"renamed": False, "error": "not_found"}, status=404)

    # user = user_qs.first()
    
    payload = json.loads(request.body)
    
    print("PAYLOAD: ", payload)

    username = payload.get("username", False)
    password = payload.get("password", False)
    is_active = payload.get("is_active", True)
    role = payload.get("role", "member")
    
    if role not in ["admin", "member"]:
        return JsonResponse({"renamed": False}, status=403)
    
    # if request.user.is_member():
    #     return JsonResponse({"renamed": False}, status=403)
        
    if not request.user.is_super_admin() and role == "admin":
        return JsonResponse({"renamed": False}, status=403)
    
    if not request.user.is_super_admin() and role == "super admin":
        return JsonResponse({"renamed": False}, status=403)
    
    if username and password and not User.objects.filter(username__iexact=username).exists():
        print('NO EXISTING USER')
        user = User.objects.create_user(username=username, password=password, is_active=is_active, role=role)
    
    try:
        user_qs =  User.objects.filter(pk=user.id)
        print('FOUND USER: ', user_qs)
    except User.DoesNotExist:
        return JsonResponse({"renamed": False, "error": "not_found"}, status=404)

    user_dict = serialize_users(user_qs)[0]
    
    if username and password and not User.objects.filter(username__iexact=username).exclude(pk=user.id).exists():
        # metrics, summary = compute_email_metrics_and_summary(environment)
        print('GOOD!')
        return JsonResponse({"renamed": True, "user": user_dict}, status=200)
    print('ERROR ???????')
    return JsonResponse({"renamed": False}, status=404)

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.JSON)
@require_http_methods(["POST"])
def edit_user(request, user_id):
    """
    Endpoint: /api/emails/<email_id>/delete/
    Minimal delete endpoint. Performs the delete and returns deletion status.
    (This one performs a single-line DB action; it's intentionally minimal.)
    """
    print('EDITING...')
    
    try:
        user_qs =  User.objects.filter(pk=user_id)
        print('FOUND USER: ', user_qs)
    except User.DoesNotExist:
        return JsonResponse({"renamed": False, "error": "not_found"}, status=404)

    user = user_qs.first()
    
    payload = json.loads(request.body)
    
    print("PAYLOAD: ", payload)

    # username = payload.get("username", False)
    is_active = payload.get("is_active", True)
    role = payload.get("role", "member")
    
    if role not in ["admin", "member"]:
        return JsonResponse({"renamed": False}, status=403)
    
    if request.user == user:
        return JsonResponse({"renamed": False}, status=403)
    
    # if request.user.is_member():
    #     return JsonResponse({"renamed": False}, status=403)
        
    if not request.user.is_super_admin() and role == "admin":
        return JsonResponse({"renamed": False}, status=403)
    
    if not request.user.is_super_admin() and role == "super admin":
        return JsonResponse({"renamed": False}, status=403)
    
    if not request.user.is_super_admin() and not user.is_member():
        return JsonResponse({"renamed": False}, status=403)
    
    # USER_LIMIT = 3
    
    # if User.objects.filter(is_active=True).count() == USER_LIMIT:
    #     return JsonResponse({"renamed": False}, status=404)
    
    # if username and not User.objects.filter(username__iexact=username).exclude(pk=user.id).exists():
    # print('NO EXISTING USERNAME')
    # user.username = username
    user.is_active = is_active
    user.role = role
    user.save()
    
    user_dict = serialize_users(user_qs)[0]
    
    # if username and not User.objects.filter(username__iexact=username).exclude(pk=user.id).exists():
        # metrics, summary = compute_email_metrics_and_summary(environment)
    return JsonResponse({"renamed": True, "user": user_dict}, status=200)

    # return JsonResponse({"renamed": False}, status=404)


@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.HTML)
def create_schema(request):
    if request.method == "POST":
        # form = SchemaForm(request.POST, initial={"user": request.user})
        form = SchemaForm(request.POST)
        print("JSON:",request.POST["schema_json"])
        if form.is_valid():
            schema = form.save(commit=False)
            schema.user = request.user
            schema.save()
            return redirect("schema_list")
        else:
            print('BAD FORM')
            return render(request, "create_schema.html", {"form": form})
    # form = SchemaForm(initial={"user": request.user})
    form = SchemaForm()
    return render(request, "create_schema.html", {"form": form})

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.HTML)
def edit_schema(request, schema_id):
    schema = get_object_or_404(Schema, id=schema_id)

    # if schema.is_locked:
    #     # Optional: allow editing metadata only
    #     form = SchemaForm(
    #         instance=schema,
    #         disabled=True  # hard disable all fields
    #     )
    #     return render(request, "schemas/schema_form.html", {
    #         "form": form,
    #         "schema": schema,
    #         "mode": "locked"
    #     })

    if request.method == "POST":
        # form = SchemaForm(request.POST, instance=schema, initial={"user": request.user})
        form = SchemaForm(request.POST, instance=schema)
        if form.is_valid():
            form.save()
            return redirect("schema_list")
        else:
            return render(request, "edit_schema.html", {
                "form": form,
                "schema": schema,
                "schema_json": json.dumps(schema.schema_json),
                'is_locked': schema.is_locked
            })
            
    # form = SchemaForm(instance=schema, initial={"user": request.user})
    form = SchemaForm(instance=schema)
    return render(request, "edit_schema.html", {
        "form": form,
        "schema": schema,
        "schema_json": json.dumps(schema.schema_json),
        'is_locked': schema.is_locked
    })

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN], view_type=ViewType.HTML)
def delete_schema(request, schema_id):
    schema = get_object_or_404(Schema, id=schema_id)
    schema.delete()
    return redirect("schema_list")

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.HTML)
def create_environment(request):
    if request.method == "POST":
        # form = EnvironmentForm(request.POST, user=request.user)
        form = EnvironmentForm(request.POST)
        if form.is_valid():
            env = form.save(commit=False)
            env.user = request.user
            env.save()
            # optionally redirect to environment detail page
            return redirect("dashboard")
    else:
        # form = EnvironmentForm(user=request.user)
        form = EnvironmentForm()

    return render(request, "create_env.html", {"form": form})

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN, Roles.ADMIN], view_type=ViewType.HTML)
def edit_environment(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    if request.method == "POST":
        # form = EnvironmentForm(request.POST, instance=environment, user=request.user)
        form = EnvironmentForm(request.POST, instance=environment)
        if form.is_valid():
            env = form.save(commit=False)
            env.user = request.user
            env.save()
            # optionally redirect to environment detail page
            return redirect("dashboard")
    else:
        # form = EnvironmentForm(user=request.user, instance=environment)
        form = EnvironmentForm(instance=environment)

    return render(request, "edit_env.html", {"form": form})

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN], view_type=ViewType.HTML)
def delete_environment(request, env_id):
    environment = get_object_or_404(Environment, id=env_id)
    environment.delete()
    return redirect("dashboard")

def _get_available_filters():
    if _CACHE_ENABLED:
        cached = cache.get(_AVAILABLE_FILTERS_CACHE_KEY)
        if cached:
            print("GETTING FROM CACHE")
            return cached

    # Build users list as {id, username}, actions and target_types as simple arrays.
    print("GETTING FROM SERVER")
    users_qs = (
        AuditLog.objects
        .exclude(user__isnull=True)
        .values("user__id", "user__username")
        .distinct()
        .order_by("user__username")
    )

    users = [{"id": u["user__id"], "username": u["user__username"]} for u in users_qs]

    actions = list(AuditLog.objects.values_list("action", flat=True).distinct())
    target_types = list(AuditLog.objects.values_list("target_type", flat=True).distinct())

    data = {
        "users": users,
        "actions": list(set(actions)),
        "target_types": list(set(target_types)),
    }
    print('DATA: ', data)
    if _CACHE_ENABLED:
        cache.set(_AVAILABLE_FILTERS_CACHE_KEY, data, _AVAILABLE_FILTERS_TTL)
    return data

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN], view_type=ViewType.JSON)
def audit_logs_api(request):
    """
    GET /api/audit-logs/
    - Query params:
        page (int), page_size (int)
        search (string)
        users (comma-separated user ids)
        actions (comma-separated action names)
        target_types (comma-separated target type names)
    - Returns JSON:
      {
        results: [...],
        pagination: { page, page_size, total_pages, total_count },
        available_filters: { users: [{id,username}], actions: [...], target_types: [...] },
        backend_filtering: bool
      }
    """
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 25))

    # Parsing incoming comma-separated params
    search = request.GET.get("search", "").strip()
    users_raw = request.GET.get("users", "")
    actions_raw = request.GET.get("actions", "")
    target_types_raw = request.GET.get("target_types", "")

    # inside audit_logs_api, after parsing other params:
    start_date_raw = request.GET.get("start_date", "").strip()
    end_date_raw = request.GET.get("end_date", "").strip()

    # parse safely (YYYY-MM-DD)
    def parse_date_ymd(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    start_date = parse_date_ymd(start_date_raw)
    end_date = parse_date_ymd(end_date_raw)


    users = [u for u in users_raw.split(",") if u]
    actions = [a for a in actions_raw.split(",") if a]
    target_types = [t for t in target_types_raw.split(",") if t]

    # Start base queryset
    qs = AuditLog.objects.select_related("user").order_by("-created_at")

    total_count = qs.count()

    # Decide whether to apply backend filters
    use_backend_filters = total_count >= AUDIT_LOG_BACKEND_FILTER_THRESHOLD

    if use_backend_filters:
        # Backend search across a handful of fields
        print('HANDLING SEARCH + FILTERS...')
        if search:
            qs = qs.filter(
                Q(action__icontains=search)
                | Q(target__icontains=search)
                | Q(target_type__icontains=search)
                | Q(user__username__icontains=search)
            )

        if users:
            # users are expected to be ids — coerce to ints where possible
            user_ids = []
            for u in users:
                try:
                    user_ids.append(int(u))
                except ValueError:
                    # ignore non-int entries
                    continue
            if user_ids:
                qs = qs.filter(user__id__in=user_ids)

        if actions:
            qs = qs.filter(action__in=actions)

        if target_types:
            qs = qs.filter(target_type__in=target_types)
            
        # apply backend filters (if you're using backend filtering — always good)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    results = []
    for log in page_obj.object_list:
        results.append({
            "id": log.id,
            "user": {
                "id": log.user.id if log.user else None,
                "username": log.user.username if log.user else "System",
                "role": log.user_role,
            },
            "action": log.action,
            "target": log.target,
            "target_type": log.target_type,
            "metadata": log.metadata,
            "created_at": log.created_at.isoformat(),
        })

    available_filters = _get_available_filters()

    return JsonResponse({
        "results": results,
        "pagination": {
            "page": page_obj.number,
            "page_size": page_size,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
        },
        "available_filters": available_filters,
        "backend_filtering": use_backend_filters,
    })

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN], view_type=ViewType.HTML)
def export_audit_logs_csv(request):
    """
    Streams filtered audit logs as CSV.
    Respects all filters + search.
    Ignores pagination.
    """

    # Parsing incoming comma-separated params
    search = request.GET.get("search", "").strip()
    users_raw = request.GET.get("users", "")
    actions_raw = request.GET.get("actions", "")
    target_types_raw = request.GET.get("target_types", "")

    # inside audit_logs_api, after parsing other params:
    start_date_raw = request.GET.get("start_date", "").strip()
    end_date_raw = request.GET.get("end_date", "").strip()

    # parse safely (YYYY-MM-DD)
    def parse_date_ymd(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    start_date = parse_date_ymd(start_date_raw)
    end_date = parse_date_ymd(end_date_raw)


    users = [u for u in users_raw.split(",") if u]
    actions = [a for a in actions_raw.split(",") if a]
    target_types = [t for t in target_types_raw.split(",") if t]

    # Start base queryset
    qs = AuditLog.objects.select_related("user").order_by("-created_at")

    total_count = qs.count()

    # Decide whether to apply backend filters
    use_backend_filters = total_count >= AUDIT_LOG_BACKEND_FILTER_THRESHOLD

    if use_backend_filters:
        # Backend search across a handful of fields
        print('HANDLING SEARCH + FILTERS...')
        if search:
            qs = qs.filter(
                Q(action__icontains=search)
                | Q(target__icontains=search)
                | Q(target_type__icontains=search)
                | Q(user__username__icontains=search)
            )

        if users:
            # users are expected to be ids — coerce to ints where possible
            user_ids = []
            for u in users:
                try:
                    user_ids.append(int(u))
                except ValueError:
                    # ignore non-int entries
                    continue
            if user_ids:
                qs = qs.filter(user__id__in=user_ids)

        if actions:
            qs = qs.filter(action__in=actions)

        if target_types:
            qs = qs.filter(target_type__in=target_types)
            
        # apply backend filters (if you're using backend filtering — always good)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

   
    # ---------------------------
    # Streaming generator
    # ---------------------------
    pseudo_buffer = Echo()
    writer = csv.writer(pseudo_buffer)

    def generate():
        # Header row
        yield writer.writerow([
            "ACTOR",
            "ROLE",
            "ACTION",
            "TARGET",
            "TARGET TYPE",
            "DATE",
            "METADATA"
            # "IP Address"
        ])

        # Use iterator() for memory efficiency
        for log in qs.iterator(chunk_size=2000):
            yield writer.writerow([
                log.user.username if log.user else "System",
                log.user.role if log.user else "",
                log.action,
                log.target,
                log.target_type,
                log.created_at.isoformat(),
                log.metadata
            ])

    response = StreamingHttpResponse(
        generate(),
        content_type="text/csv"
    )

    response["Content-Disposition"] = 'attachment; filename="audit_logs.csv"'

    return response

@login_required
@require_roles(allowed_roles=[Roles.SUPER_ADMIN], view_type=ViewType.HTML)
def view_audit_logs(request):
    return render(request, "audit_logs.html")
