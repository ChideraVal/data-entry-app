from django.db import models
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.forms import ValidationError
from .utils.cryptography import decrypt_value
from django.conf import settings

# user = get_user_model()

ROLES = (
    ('super admin', 'Super Admin'),
    ('admin', 'Admin'),
    ('member', 'Member') 
)

class User(AbstractUser):
    role = models.CharField(max_length=255, choices=ROLES, default=ROLES[2][0])
    # has_changed_password = models.BooleanField(default=False, help_text="If the user has changed their password on first login")

    USERNAME_FIELD = "username"

    def is_super_admin(self):
        return self.role == "super admin"
    
    def is_admin(self):
        return self.role == "admin"
    
    def is_member(self):
        return self.role == "member"
    
    def __str__(self):
        return self.username
    

PROCESS_STATUS = (
    ('pending', 'Pending'),
    ('successful', 'Successful'),
    ('failed', 'Failed'),
)

# user = User

# ---------------------------------------------------------
# INTERNAL EMAIL
# ---------------------------------------------------------
class InternalEmail(models.Model):
    subject = models.CharField(max_length=255)
    sender = models.CharField(max_length=255)
    body = models.TextField(null=True, blank=True)
    date_recieved = models.DateTimeField()

    # Store attachments (raw bytes)
    attachments = models.JSONField(default=list, blank=True)
    message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    total_file_size = models.IntegerField(default=0)
    

    def __str__(self):
        return f"{self.subject} from {self.sender}"
    

# ---------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------
class Schema(models.Model):
    """
    Reusable schema definition.
    Can be attached to many environments.
    Becomes immutable once used for extraction.
    """

    # user = models.ForeignKey(
    #     User,
    #     on_delete=models.CASCADE,
    #     related_name="schemas"
    # )

    name = models.CharField(
        max_length=150,
        help_text="Human-friendly name for this schema"
    )

    description = models.TextField(
        blank=True,
        max_length=200
    )

    schema_json = models.JSONField(
        help_text="Typed JSON used to generate Pydantic models"
    )

    # 🔒 Lock once any environment extracts data using this schema
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked after first successful data extraction"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # unique_together = ("user", "name")
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


from django.db import models
from django.conf import settings

class Environment(models.Model):
    """
    Stores environment config. Many environments can reference the same Schema.
    """
    # user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="environments")
    name = models.CharField(max_length=120)

    schema = models.ForeignKey(Schema, null=True, blank=True, on_delete=models.SET_NULL, related_name="environments")

    imap_email = models.EmailField(max_length=255, blank=True)
    imap_password = models.CharField(max_length=255, blank=True)  # consider encrypting in production
    imap_host = models.CharField(max_length=255, blank=True)

    # JSON lists
    email_folders = models.JSONField(default=list, blank=True)                # e.g. ["INBOX", "invoices"]
    document_types = models.JSONField(default=list, blank=True)              # e.g. ["invoice","card statement"]
    allowed_senders = models.JSONField(default=list, blank=True)             # list of email addresses / patterns
    allowed_subject_keywords = models.JSONField(default=list, blank=True)    # list of strings
    blocked_subject_keywords = models.JSONField(default=list, blank=True)    # list of strings

    # allowed file types (store as list of strings)
    allowed_file_types = models.JSONField(default=list, blank=True)          # e.g. ["pdf","docx","jpg"]

    require_attachment = models.BooleanField(default=False)

    since_date = models.DateField(null=True, blank=True)

    has_extracted_data = models.BooleanField(default=False)  # prevents certain changes after extraction

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name}"

    def get_imap_password(self):
        return decrypt_value(self.imap_password)

# ---------------------------------------------------------
# ENVIRONMENT EMAIL
# ---------------------------------------------------------
class EnvironmentEmail(models.Model):
    """
    This is an email that exists inside the environment.
    The same physical Gmail email can exist in many environments,
    because each environment processes emails independently.
    """
    environment = models.ForeignKey(
        Environment,
        on_delete=models.CASCADE,
        related_name="environment_emails"
    )

    # Link to global internal email table
    internal_email = models.ForeignKey(
        "InternalEmail",     # You already have this model
        on_delete=models.CASCADE,
        related_name="environment_links"
    )
    
    status = models.CharField(max_length=255, choices=PROCESS_STATUS, default=PROCESS_STATUS[0][0])
    # max_size = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("environment", "internal_email")

    def __str__(self):
        return f"Email: {self.internal_email.subject} in {self.environment.name}"


# class InternalFile(models.Model):
#     attachments = models.JSONField(default=list, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     total_file_size = models.IntegerField(default=0)
    

class EnvironmentUpload(models.Model):
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name="environment_uploads")
    # Link to global internal file table
    # internal_file = models.ForeignKey(
    #     "InternalFile",     # You already have this model
    #     on_delete=models.CASCADE,
    #     related_name="uploads"
    # )
    name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=255, choices=PROCESS_STATUS, default=PROCESS_STATUS[0][0])
    # source = models.CharField(max_length=30)  # email, upload, whatsapp
    attachments = models.JSONField(default=list, blank=True)
    total_file_size = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Upload: {self.name} in {self.environment.name}"


# ---------------------------------------------------------
# EXTRACTION RESULT
# ---------------------------------------------------------
class ExtractionResult(models.Model):
    """
    Stores the AI-parsed structured data for an EnvironmentEmail.
    Only one ExtractionResult per EnvironmentEmail.
    """

    environment = models.ForeignKey(
        Environment,
        on_delete=models.CASCADE,
        related_name="results"
    )

    environment_email = models.OneToOneField(
        EnvironmentEmail,
        on_delete=models.CASCADE,
        related_name="result",
        null=True,
        blank=True
    )
    
    environment_upload = models.OneToOneField(
        EnvironmentUpload,
        on_delete=models.CASCADE,
        related_name="result",
        null=True,
        blank=True
    )

    raw_json = models.JSONField(blank=True, null=True)  # store full AI JSON
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.environment_upload:
            return f"Result for {self.environment_upload}"
        return f"Result for {self.environment_email}"


class AuditLog(models.Model):
    # user may be null (system actions)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    # keep a cached role string at time of event to avoid joins later
    user_role = models.CharField(max_length=80, blank=True, null=True)

    action = models.CharField(max_length=150)        # e.g. "created", "updated", "approved"
    target = models.CharField(max_length=255)        # human readable target name
    target_type = models.CharField(max_length=100)   # e.g. "user", "schema", "environment"

    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["user"]),
            models.Index(fields=["action"]),
            models.Index(fields=["target_type"]),
        ]

    def __str__(self):
        actor = self.user.username if self.user else "System"
        return f"{actor} {self.action} {self.target_type}:{self.target} at {self.created_at}"


class TaskLock(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


