# forms.py
from django import forms
import re
from .models import Schema, User
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm, PasswordChangeForm
import random

# User = user

class CustomAuthForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.fields["username"].widget.attrs['autocomplete'] = 'off'
        # self.fields["username"].label = 'Email Address'


class CustomUserCreationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.fields["username"].widget.attrs['autocomplete'] = 'off'
        self.fields["username"].widget.attrs['autofocus'] = 'on'
        # self.fields["email"].widget.attrs['autocomplete'] = 'off'
        # self.fields["email"].label = 'Email Address'

    
    class Meta:
        model = User
        fields = ['username']


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ['username']
        widgets = {
            'username': forms.TextInput(attrs={'autocomplete': 'off'})
        }

        labels = {
            'email': 'Email Address'
        }

        error_messages = {
            'email': {
                'unique': "This email is already associated with another account."
            }
        }

        help_texts = {
            'email': "When you change your email address, the new address isn't set immediately, instead an email will be sent to the new address with a link to verify the new address. Click the link to finalize changes."
        }

def validate_schema_json(schema_json: dict):
    if not isinstance(schema_json, dict) or not schema_json:
        raise ValueError("Schema must be a non-empty object")

    def walk(node):
        if isinstance(node, str):
            return
        if isinstance(node, dict):
            t = node.get("type")
            if t == "object":
                props = node.get("properties")
                if not props or not isinstance(props, dict):
                    raise ValueError("Object must have at least one property")
                for v in props.values():
                    walk(v)
            elif t == "array":
                if "items" not in node:
                    raise ValueError("Array must define items")
                walk(node["items"])
            else:
                raise ValueError(f"Invalid type: {t}")

    for value in schema_json.values():
        walk(value)


def normalize_field_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)   # replace non-alphanumerics
    name = re.sub(r"_+", "_", name)           # collapse underscores
    return name.strip("_")

SYSTEM_FIELDS_RAW = {
    "fail reason",
    "email id",
    "upload id"
}

SYSTEM_FIELDS = {
    normalize_field_name(name) for name in SYSTEM_FIELDS_RAW
}

def walk_schema(schema: dict) -> bool:
    """
    Returns True if a reserved system field is found anywhere.
    """
    for key, val in schema.items():
        normalized = normalize_field_name(key)
        if normalized in SYSTEM_FIELDS:
            return True

        # Recurse into nested objects
        if isinstance(val, dict):
            if val.get("type") == "object":
                props = val.get("properties", {})
                if walk_schema(props):
                    return True

            # Recurse into array items
            if val.get("type") == "array":
                items = val.get("items", {})
                if isinstance(items, dict) and items.get("type") == "object":
                    if walk_schema(items.get("properties", {})):
                        return True

    return False



class SchemaForm(forms.ModelForm):
    class Meta:
        model = Schema
        fields = ["name", "description", "schema_json"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "id": "schemaName",
                "oninput": "renderAndValidate()",
                "placeholder": "e.g. Invoice Schema"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional description"
            }),
            "schema_json": forms.Textarea(attrs={
                "class": "form-control",
                "id": "formjsonPreview",
                "hidden": "true",
                "rows": 14,
                "placeholder": "Typed JSON schema"
            }),
        }
    
    def clean_name(self):
        name = self.cleaned_data['name']
        user = self.instance.user if self.instance.pk else self.initial.get('user')
        
        schemas = Schema.objects.filter(name__iexact=name, user=user)
        
        if self.instance.pk:
            schemas = Schema.objects.filter(name__iexact=name, user=user).exclude(pk=self.instance.pk)
        
        if schemas.exists():
            raise forms.ValidationError(f"You already have a schema with this name")
        
        return name
            
    
    # def clean_schema_json(self):
    #     """
    #     Basic sanity checks.
    #     Deep validation should already happen in the frontend,
    #     but we still guard the backend.
    #     """
    #     schema = self.cleaned_data["schema_json"]
    #     print('SCHEMA:', schema)

    #     # if not isinstance(schema, dict):
    #     #     raise forms.ValidationError("Schema must be a JSON object")

    #     # if not schema:
    #     #     raise forms.ValidationError("Schema cannot be empty")
    #     try:
    #         validate_schema_json(schema)
    #         return schema
    #     except Exception as e:
    #         print('ERROR WHILE VALIDATING SCHEMA:', e)
    #         raise forms.ValidationError(str(e))
    
    
    
    def clean_schema_json(self):
        schema_json = self.cleaned_data.get("schema_json")
        
        # Must be an object
        if not isinstance(schema_json, dict):
            raise ValidationError("Schema must be a JSON object.")

        # 🔒 Prevent schema change after extraction
        if self.instance.pk and self.instance.is_locked:
            if schema_json != self.instance.schema_json:
                raise ValidationError(
                    "Schema fields cannot be changed after this schema has been used by your environment(s) to process data."
                )
        
        # prevent creation of system fields in schema (email/upload id, fail reason)
        if walk_schema(schema_json):
            raise ValidationError(
                "Schema contains one or more reserved system fields "
                "(e.g. fail reason, email id, upload id). These fields are managed by the system."
            )

        return schema_json
    

# apps/yourapp/forms.py
import datetime
from django import forms
from django.core.exceptions import ValidationError
from .models import Environment, Schema

from .utils.cryptography import encrypt_value


FILE_TYPE_CHOICES = [
    ("pdf", "PDF (.pdf)"),
    ("png", "PNG (.png)"),
    ("jpg", "JPG (.jpg)"),
    ("jpeg", "JPEG (.jpeg)"),
    ("webp", "WEBP (.webp)"),
    ("txt", "Text (.txt)")
]

DOCUMENT_TYPE_CHOICES = [
    ('invoice', 'Invoice'),
    ('purchase order', 'Purchase Order'),
    ('receipt', 'Receipt'),
    ('bank statement', 'Bank Statement'),
    ('credit card statement', 'Credit Card Statement'),
    ('utility bill', 'Utility Bill'),
    ('tax document', 'Tax Document'),
    ('medical report', 'Medical Report'),
    ('prescription', 'Prescription'),
    ('lab test result', 'Lab Test Result'),
    ('insurance policy document', 'Insurance Policy Document'),
    ('insurance claim form', 'Insurance Claim Form'),
    ('employment contract', 'Employment Contract'),
    ('offer letter', 'Offer Letter'),
    ('salary slip', 'Salary Slip'),
    ('delivery note', 'Delivery Note'),
    ('shipping label', 'Shipping Label'),
    ('packing slip', 'Packing Slip'),
    ('rental agreement', 'Rental Agreement'),
    ('lease contract', 'Lease Contract'),
    ('legal notice', 'Legal Notice'),
    ('court document', 'Court Document'),
    ('passport scan', 'Passport Scan'),
    ('id card scan', 'Id Card Scan'),
    ('driver license scan', 'Driver License Scan'),
    ('boarding pass', 'Boarding Pass'),
    ('travel itinerary', 'Travel Itinerary'),
    ('hotel booking confirmation', 'Hotel Booking Confirmation'),
    ('flight ticket', 'Flight Ticket'),
    ('medical bill', 'Medical Bill'),
    ('donation receipt', 'Donation Receipt'),
    ('academic transcript', 'Academic Transcript'),
    ('certificate', 'Certificate'),
    ('warranty document', 'Warranty Document'),
    ('maintenance report', 'Maintenance Report'),
    ('test report', 'Test Report'),
    ('safety inspection report', 'Safety Inspection Report'),
    ('handwritten notes', 'Handwritten Notes'),
    ('meeting minutes', 'Meeting Minutes'),
    ('printed letter', 'Printed Letter'),
    ('business card', 'Business Card'),
    ('expense report', 'Expense Report'),
    ('shopping list', 'Shopping List'),
    ('to do list', 'To Do List'),
    ('delivery receipt', 'Delivery Receipt'),
    ('service invoice', 'Service Invoice'),
    ('property deed', 'Property Deed'),
    ('bank alert document', 'Bank Alert Document'),
    ('payment confirmation', 'Payment Confirmation'),
    ('transaction summary', 'Transaction Summary'),
    ('quote or estimate', 'Quote Or Estimate'),
    ('research paper', 'Research Paper'),
    ('brochure or flyer', 'Brochure Or Flyer')
]


def parse_lines_to_list(raw_text):
    """
    Parse newline-separated textarea into a clean list.
    - Trims whitespace
    - Ignores empty lines
    - Deduplicates while preserving order
    """
    if not raw_text:
        return []

    items = []
    seen = set()

    for line in raw_text.splitlines():
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            items.append(value)

    return items


class EnvironmentForm(forms.ModelForm):
    # ------------------------
    # Textarea-backed list fields
    # ------------------------

    email_folders_text = forms.CharField(
        required=True,  # ✅ REQUIRED
        label="Email folders (one per line)",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "INBOX\nInvoices\nArchive/2025"}
        ),
    )

    # document_types_text = forms.CharField(
    #     required=True,  # ✅ REQUIRED
    #     label="Document types (one per line)",
    #     widget=forms.Textarea(
    #         attrs={"rows": 3, "placeholder": "invoice\ncard statement\ntax report"}
    #     ),
    # )
    
    document_types = forms.MultipleChoiceField(
        required=True,
        choices=DOCUMENT_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Document types",
    )

    allowed_senders_text = forms.EmailField(
        required=False,
        label="Allowed senders (one per line)",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "billing@amazon.com\n@stripe.com"}
        ),
    )

    allowed_subject_keywords_text = forms.CharField(
        required=False,
        label="Allowed subject keywords (one per line)",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "invoice\npayment due"}
        ),
    )

    blocked_subject_keywords_text = forms.CharField(
        required=False,
        label="Blocked subject keywords (one per line)",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "spam\nnewsletter"}
        ),
    )

    # ------------------------
    # File types & flags
    # ------------------------

    allowed_file_types = forms.MultipleChoiceField(
        required=False,
        choices=FILE_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Allowed file types",
    )

    require_attachment = forms.BooleanField(
        required=False,
        label="Require attachment",
    )

    # ------------------------
    # Model fields
    # ------------------------

    class Meta:
        model = Environment
        fields = [
            "name",
            "schema",
            "document_types",
            "imap_email",
            "imap_password",
            "imap_host",
            "since_date",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Environment name"}),
            "schema": forms.Select(),
            "imap_email": forms.EmailInput(attrs={"placeholder": "imap@example.com"}),
            "imap_password": forms.PasswordInput(attrs={"placeholder": "IMAP password"}),
            "imap_host": forms.TextInput(attrs={"placeholder": "imap.mail.server:993"}),
            "since_date": forms.DateInput(attrs={"type": "date"}),
        }

    # ------------------------
    # Init
    # ------------------------

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Required core fields
        self.fields["name"].required = True
        self.fields["imap_email"].required = True
        self.fields["imap_password"].required = True
        self.fields["imap_host"].required = True
        self.fields["since_date"].required = True

        # Schema is not optional
        self.fields["schema"].required = True

        # Limit schema dropdown to user's schemas
        # if self.user is not None:
        #     self.fields["schema"].queryset = Schema.objects.filter(
        #         user=self.user
        #     ).order_by("-updated_at")
        
        # Limit schema dropdown to all schemas
        if self.user is not None:
            self.fields["schema"].queryset = Schema.objects.all().order_by("-updated_at")

        # Populate textarea fields when editing
        if self.instance.pk:
            self.fields["email_folders_text"].initial = "\n".join(
                self.instance.email_folders or []
            )
            # self.fields["document_types_text"].initial = "\n".join(
            #     self.instance.document_types or []
            # )
            
            self.fields["document_types"].initial = (
                self.instance.document_types or []
            )
            
            self.fields["allowed_senders_text"].initial = "\n".join(
                self.instance.allowed_senders or []
            )
            self.fields["allowed_subject_keywords_text"].initial = "\n".join(
                self.instance.allowed_subject_keywords or []
            )
            self.fields["blocked_subject_keywords_text"].initial = "\n".join(
                self.instance.blocked_subject_keywords or []
            )
            self.fields["allowed_file_types"].initial = (
                self.instance.allowed_file_types or []
            )
            self.fields["require_attachment"].initial = (
                self.instance.require_attachment
            )
        
        # Lock Schema + doc types if environment has extracted data
        if self.instance.pk and self.instance.has_extracted_data:
            self.fields["schema"].disabled = True
            self.fields["document_types"].disabled = True
            

    # ------------------------
    # Validation
    # ------------------------

    def clean_name(self):
        name = self.cleaned_data['name']
        
        environments = Environment.objects.filter(name__iexact=name, user=self.user)
        
        if self.instance.pk:
            environments = Environment.objects.filter(name__iexact=name, user=self.user).exclude(pk=self.instance.pk)
        
        if environments.exists():
            raise forms.ValidationError(f"You already have an environment with this name")
        
        return name
    
    def clean_since_date(self):
        value = self.cleaned_data["since_date"]
        if value > datetime.date.today():
            raise ValidationError("Since date cannot be in the future.")
        return value

    def clean_email_folders_text(self):
        folders = parse_lines_to_list(self.cleaned_data.get("email_folders_text"))
        if not folders:
            raise ValidationError("At least one email folder is required.")
        return folders

    # def clean_document_types_text(self):
    #     doc_types = parse_lines_to_list(self.cleaned_data.get("document_types_text"))
    #     if not doc_types:
    #         raise ValidationError("At least one document type is required.")

    #     # 🔒 Prevent change after extraction
    #     if self.instance.pk and self.instance.has_extracted_data:
    #         if doc_types != (self.instance.document_types or []):
    #             raise ValidationError(
    #                 "Document types cannot be changed after this environment has processed data."
    #             )
    #     return doc_types
    
    def clean_document_types(self):
        doc_types = self.cleaned_data.get("document_types")
        if not doc_types:
            raise ValidationError("At least one document type is required.")

        # 🔒 Prevent change after extraction
        if self.instance.pk and self.instance.has_extracted_data:
            if doc_types != (self.instance.document_types or []):
                raise ValidationError(
                    "Document types cannot be changed after this environment has processed data."
                )
        return doc_types

    def clean_schema(self):
        schema = self.cleaned_data.get("schema")

        # 🔒 Prevent schema change after extraction
        if self.instance.pk and self.instance.has_extracted_data:
            if schema != self.instance.schema:
                raise ValidationError(
                    "Schema cannot be changed after this environment has processed data."
                )
        return schema
    
    

    def clean_allowed_senders_text(self):
        return parse_lines_to_list(self.cleaned_data.get("allowed_senders_text"))

    def clean_allowed_subject_keywords_text(self):
        return parse_lines_to_list(self.cleaned_data.get("allowed_subject_keywords_text"))

    def clean_blocked_subject_keywords_text(self):
        return parse_lines_to_list(self.cleaned_data.get("blocked_subject_keywords_text"))

    # ------------------------
    # Save
    # ------------------------

    def save(self, commit=True):
        instance = super().save(commit=False)

        instance.imap_password = encrypt_value(self.cleaned_data["imap_password"])

        instance.email_folders = self.cleaned_data["email_folders_text"]
        instance.document_types = self.cleaned_data["document_types"]
        instance.allowed_senders = self.cleaned_data["allowed_senders_text"]
        instance.allowed_subject_keywords = self.cleaned_data["allowed_subject_keywords_text"]
        instance.blocked_subject_keywords = self.cleaned_data["blocked_subject_keywords_text"]

        instance.allowed_file_types = self.cleaned_data.get("allowed_file_types", [])
        instance.require_attachment = self.cleaned_data.get("require_attachment", False)

        if commit:
            instance.save()

        return instance
