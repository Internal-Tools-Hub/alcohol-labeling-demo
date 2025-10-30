from typing import Tuple, Any
import logging
import os
from datetime import timedelta
from django.conf import settings
from google.cloud import storage
from google import genai
from google.genai import types as genai_types


logger = logging.getLogger(__name__)


def upload_file_to_gcs(local_file_path: str, destination_path: str) -> Tuple[str, str]:
    """Upload a local file to GCS and return (gs_uri, public_url).

    Logs detailed diagnostics around the upload process for easier debugging.
    """
    gs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{destination_path}"
    try:
        file_exists = os.path.exists(local_file_path)
        file_size = os.path.getsize(local_file_path) if file_exists else -1
        logger.info(
            "GCS upload start: local='%s' exists=%s size=%s bytes → bucket='%s' dest='%s' uri='%s'",
            local_file_path,
            file_exists,
            file_size,
            settings.GCS_BUCKET_NAME,
            destination_path,
            gs_uri,
        )

        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(destination_path)

        # Try to infer content type from filename; fall back to octet-stream
        content_type = None
        try:
            import mimetypes

            content_type = mimetypes.guess_type(local_file_path)[0]
        except Exception:
            content_type = None

        if content_type:
            blob.upload_from_filename(local_file_path, content_type=content_type)
        else:
            blob.upload_from_filename(local_file_path)

        public_url = blob.public_url
        logger.info(
            "GCS upload success: uri='%s' public_url='%s'",
            gs_uri,
            public_url,
        )
        return gs_uri, public_url
    except Exception as exc:
        logger.exception(
            "GCS upload failed: local='%s' → uri='%s' error=%s",
            local_file_path,
            gs_uri,
            exc,
        )
        raise


def generate_signed_url(gs_uri: str, seconds: int = 900) -> str:
    """Generate a V4 signed URL for a gs:// URI. Returns empty string on failure."""
    try:
        if not gs_uri or not gs_uri.startswith("gs://"):
            return ""
        without_scheme = gs_uri[5:]
        bucket_name, blob_name = without_scheme.split("/", 1)
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        url = blob.generate_signed_url(version="v4", expiration=timedelta(seconds=int(seconds)), method="GET")
        return url
    except Exception as exc:
        logger.exception("generate_signed_url failed for uri='%s': %s", gs_uri, exc)
        return ""


def call_gemini_with_image_bytes(image_bytes: bytes, model: str) -> Any:
    """Call Gemini model with image bytes and return parsed response text or dict."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = (
        "Analyze this alcohol beverage label image and extract JSON with fields: "
        "brand_name, product_type, alcohol_content (number), net_contents, "
        "government_warning_present (boolean), all_text_found, confidence (0-1)."
    )
    part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    response = client.models.generate_content(
        model=model or settings.GEMINI_MODEL,
        contents=[prompt, part],
        config=genai_types.GenerateContentConfig(temperature=0.1, max_output_tokens=1000),
    )
    return response.text


