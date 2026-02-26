from django.contrib import admin
from .models import InternalEmail, Schema, Environment, EnvironmentEmail, EnvironmentUpload, ExtractionResult, TaskLock, AuditLog
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

User = get_user_model()


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Show fields in the user edit page
    fieldsets = UserAdmin.fieldsets + (
        ("Extra info", {
            "fields": ("role",)
        }),
    )
    
    # Show fields when creating a user in admin
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Extra info", {
            "fields": ("role",)
        }),
    )
    
    list_display = UserAdmin.list_display + ("role",)
    
    def get_app_label(self, request):
        return "auth"


@admin.register(InternalEmail)
class InternalEmailAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "date_recieved", "created_at", "attachments", "total_file_size")
    readonly_fields = ("attachments",)


@admin.register(Schema)
class SchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_locked", "created_at")
    # readonly_fields = ("schema_json",)


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ("name", "imap_email", "imap_password", "imap_host", "email_folders")


@admin.register(EnvironmentEmail)
class EnvironmentEmailAdmin(admin.ModelAdmin):
    list_display = ("environment", "internal_email", "status", "created_at", "updated_at")


@admin.register(EnvironmentUpload)
class EnvironmentUploadAdmin(admin.ModelAdmin):
    list_display = ("environment", "name", "attachments", "total_file_size", "status")


@admin.register(ExtractionResult)
class ExtractionResultAdmin(admin.ModelAdmin):
    list_display = ("environment", "environment_email", "environment_upload", "environment_email__status", "environment_upload__status", "is_approved", "raw_json")
    # readonly_fields = ("raw_json",)
    

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "user_role", "action", "target", "target_type", "created_at")
    

@admin.register(TaskLock)
class TaskLockAdmin(admin.ModelAdmin):
    list_display = ("name", "is_locked", "locked_at")

