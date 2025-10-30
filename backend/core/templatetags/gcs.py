from datetime import timedelta
import logging
from urllib.parse import urlparse

from django import template
from django.conf import settings
from google.cloud import storage

register = template.Library()
logger = logging.getLogger(__name__)


def _parse_gs_uri(gs_uri: str):
    if not gs_uri or not gs_uri.startswith("gs://"):
        raise ValueError("Invalid gs uri")
    # gs://bucket/path/to/blob
    without_scheme = gs_uri[5:]
    parts = without_scheme.split("/", 1)
    bucket = parts[0]
    path = parts[1] if len(parts) > 1 else ""
    return bucket, path


@register.simple_tag
def signed_url(gs_uri: str, seconds: int = 600) -> str:
    """Return a V4 signed URL for a gs:// URI. Defaults to 10 minutes validity."""
    try:
        bucket_name, blob_name = _parse_gs_uri(gs_uri)
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        url = blob.generate_signed_url(version="v4", expiration=timedelta(seconds=int(seconds)), method="GET")
        return url
    except Exception as exc:
        logger.exception("signed_url failed for uri='%s': %s", gs_uri, exc)
        # Fallback empty to avoid breaking templates
        return ""


