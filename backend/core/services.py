from typing import Tuple, Any
import json
import re
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


def get_public_url(gs_uri: str) -> str:
    """Return public URL for a gs:// object (works if bucket/object is public)."""
    try:
        if not gs_uri or not gs_uri.startswith("gs://"):
            return gs_uri or ""
        without_scheme = gs_uri[5:]
        bucket_name, blob_name = without_scheme.split("/", 1)
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.public_url
    except Exception as exc:
        logger.exception("get_public_url failed for uri='%s': %s", gs_uri, exc)
        return gs_uri or ""


def download_gcs_bytes(gs_uri: str) -> bytes:
    """Download object bytes from GCS given a gs:// URI."""
    try:
        if not gs_uri or not gs_uri.startswith("gs://"):
            raise ValueError("download_gcs_bytes expects a gs:// URI")
        without_scheme = gs_uri[5:]
        bucket_name, blob_name = without_scheme.split("/", 1)
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {gs_uri}")
        return blob.download_as_bytes()
    except Exception as exc:
        logger.exception("download_gcs_bytes failed for uri='%s': %s", gs_uri, exc)
        raise


def delete_gcs_object(gs_uri: str) -> None:
    """Delete object from GCS given a gs:// URI."""
    try:
        if not gs_uri or not gs_uri.startswith("gs://"):
            raise ValueError("delete_gcs_object expects a gs:// URI")
        without_scheme = gs_uri[5:]
        bucket_name, blob_name = without_scheme.split("/", 1)
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
    except Exception as exc:
        logger.exception("delete_gcs_object failed for uri='%s': %s", gs_uri, exc)
        raise


def test_gcs_connection(bucket_name: str | None = None) -> bool:
    """Test GCS connectivity and minimal permissions for the configured bucket."""
    try:
        target_bucket = bucket_name or settings.GCS_BUCKET_NAME
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(target_bucket)
        required_perms = [
            'storage.objects.create',
            'storage.objects.get',
            'storage.objects.delete',
        ]
        granted = bucket.test_iam_permissions(required_perms)
        has_minimum = 'storage.objects.create' in granted and 'storage.objects.get' in granted
        if not has_minimum:
            missing = [p for p in required_perms if p not in granted]
            logger.error("GCS connection test: missing permissions on bucket %s: %s", target_bucket, ", ".join(missing))
            return False
        return True
    except Exception as exc:
        logger.exception("test_gcs_connection failed: %s", exc)
        return False

def call_gemini_with_image_bytes(image_bytes: bytes, model: str) -> Any:
    """Call Gemini with image bytes and return parsed JSON dict when possible.

    Falls back to raw text if JSON cannot be parsed.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = (
        "Analyze this alcohol beverage label image and return ONLY valid JSON with fields: "
        "brand_name (string), product_type (string), alcohol_content (number), net_contents (string), "
        "government_warning_present (boolean), all_text_found (string), confidence (0-1)."
    )
    part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    response = client.models.generate_content(
        model=model or settings.GEMINI_MODEL,
        contents=[prompt, part],
        config=genai_types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1000,
            response_mime_type="application/json",
        ),
    )
    text = response.text or ""
    # Try to parse as JSON directly
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try to extract fenced JSON block
    fenced = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    # Try to extract first JSON object heuristically
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    logger.warning("Gemini response not JSON; returning raw text")
    return text


def local_ocr_image_to_text(image_path: str) -> str:
    """Extract text from an image file using pytesseract. Returns empty string on failure.

    Note: Requires the system tesseract binary to be available in PATH.
    """
    try:
        import pytesseract
        from PIL import Image
        image = Image.open(image_path)
        # OEM 3: Default, PSM 6: Assume a single uniform block of text
        config = r"--oem 3 --psm 6"
        text = pytesseract.image_to_string(image, config=config)
        return text or ""
    except Exception as exc:
        logger.exception("local_ocr_image_to_text failed for '%s': %s", image_path, exc)
        return ""


