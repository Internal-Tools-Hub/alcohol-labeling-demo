from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimestampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class Location(TimestampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=255)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ("company", "name")

    def __str__(self) -> str:
        return f"{self.company.name} - {self.name}"


class Submission(TimestampedModel):
    STATUS_PENDING = "pending"
    STATUS_PROCESSED = "processed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True)
    # Deprecated single file; multi-image stored in SubmissionImage
    gcs_uri = models.CharField(max_length=512, blank=True)
    gemini_model = models.CharField(max_length=128, default="gemini-2.5-flash")
    gemini_response = models.JSONField(blank=True, null=True)
    # Aggregated OCR extracts for the submission (both Gemini-parsed and local OCR text)
    ocr_extract = models.JSONField(blank=True, null=True)
    # PRD fields (user-entered expected values)
    # brand_name is optional and serves as an override to the company name if different
    brand_name = models.CharField(max_length=255, blank=True)
    product_class_type = models.CharField(max_length=255)
    alcohol_content = models.CharField(max_length=50)  # store as entered, e.g., "45%"
    net_contents = models.CharField(max_length=50, blank=True)
    # Verification results summary
    verification_result = models.JSONField(blank=True, null=True)
    # Admin/seed-only metadata
    intentional_fail = models.BooleanField(default=False)
    intentional_failure_reason = models.TextField(blank=True)
    regulatory_citation = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        loc = getattr(self, "location", None)
        loc_str = loc.name if loc else "No location"
        return f"Submission {self.pk} - {self.company.name} - {loc_str}"


class SubmissionImage(TimestampedModel):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="uploads/submissions/")
    gcs_uri = models.CharField(max_length=512, blank=True)
    gemini_response = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        return f"SubmissionImage {self.pk} for submission {self.submission_id}"


class Comment(TimestampedModel):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()

    def __str__(self) -> str:
        return f"Comment {self.pk} on submission {self.submission_id} by {self.user}"


