import os
import logging
from django.contrib import messages
import json
import sys
import os
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView, View

from .forms import CompanyForm, LocationForm, SubmissionForm, CommentForm
from .models import Company, Location, Submission, SubmissionImage, Comment
from .services import upload_file_to_gcs, call_gemini_with_image_bytes, generate_signed_url, local_ocr_image_to_text
from .verification_service import verification_service

logger = logging.getLogger(__name__)


def _convert_verification_to_legacy(fields: dict, submission: Submission) -> dict:
    """
    Convert verification service results to legacy format while preserving expected/extracted values.
    """
    brand_field = fields.get("brand_name", {})
    type_field = fields.get("product_type", {})
    ac_field = fields.get("alcohol_content", {})
    net_field = fields.get("net_contents", {})
    gov_field = fields.get("government_warning", {})
    
    return {
        "brand_name": {
            "expected": brand_field.get("expected", submission.brand_name or submission.company.name),
            "extracted": brand_field.get("extracted"),
            "match": bool(brand_field.get("matched")),
        },
        "product_class_type": {
            "expected": type_field.get("expected", submission.product_class_type),
            "extracted": type_field.get("extracted"),
            "match": bool(type_field.get("matched")),
        },
        "alcohol_content": {
            "expected": ac_field.get("expected", submission.alcohol_content),
            "extracted": ac_field.get("extracted"),
            "match": bool(ac_field.get("matched")),
        },
        "net_contents": {
            "expected": net_field.get("expected", submission.net_contents),
            "extracted": net_field.get("extracted"),
            "match": bool(net_field.get("matched")),
            "optional": True,
        },
        "government_warning_present": {
            "expected": gov_field.get("expected", True),
            "extracted": gov_field.get("extracted"),
            "match": bool(gov_field.get("matched")),
        },
        "all_pass": all([
            bool(brand_field.get("matched")),
            bool(type_field.get("matched")),
            bool(ac_field.get("matched")),
            bool(net_field.get("matched")),
            bool(gov_field.get("matched")),
        ]),
    }


def _combine_verification_results(results: list, field_name: str, submission: Submission) -> dict:
    """
    Aggregate verification results across multiple images, preserving expected/extracted values.
    """
    # Get the first valid expected value from results
    expected_val = None
    for r in results:
        if isinstance(r, dict) and field_name in r:
            field_data = r.get(field_name, {})
            if isinstance(field_data, dict) and "expected" in field_data:
                expected_val = field_data.get("expected")
                break
    
    # Fallback to submission data if no expected value found
    if expected_val is None:
        if field_name == "brand_name":
            expected_val = submission.brand_name or submission.company.name
        elif field_name == "product_class_type":
            expected_val = submission.product_class_type
        elif field_name == "alcohol_content":
            expected_val = submission.alcohol_content
        elif field_name == "net_contents":
            expected_val = submission.net_contents
        elif field_name == "government_warning_present":
            expected_val = True
    
    # Check if any image matches
    match_ok = any(bool((r.get(field_name) or {}).get("match")) for r in results if isinstance(r, dict))
    
    return {
        "expected": expected_val,
        "extracted": None,  # Aggregated results don't have a single extracted value
        "match": match_ok,
    }


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = SubmissionForm()
        context["recent_submissions"] = Submission.objects.order_by("-created_at")[:10]
        return context

    def post(self, request, *args, **kwargs):
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission: Submission = form.save(commit=False)
            submission.user = request.user
            submission.status = Submission.STATUS_PENDING
            submission.save()

            try:
                # Handle simple two-file upload (front/back)
                front = self.request.FILES.get("front_image")
                back = self.request.FILES.get("back_image")
                logger.info("HomeView: received front=%s back=%s", bool(front), bool(back))
                if not front and not back:
                    messages.error(request, "Please add at least one image.")
                    return self.render_to_response({"form": form, "recent_submissions": Submission.objects.order_by("-created_at")[:10]})
                per_image_results = []
                ocr_image_results = []
                per_image_ocr_texts = []
                combined_text = ""
                for f in [front, back]:
                    if not f:
                        continue
                    img = SubmissionImage.objects.create(submission=submission, image=f)
                    local_path = img.image.path
                    filename = os.path.basename(local_path)
                    gcs_path = f"submissions/{submission.id}/{filename}"
                    gs_uri, _ = upload_file_to_gcs(local_path, gcs_path)
                    img.gcs_uri = gs_uri
                    with open(local_path, "rb") as fh:
                        image_bytes = fh.read()
                    response_text = call_gemini_with_image_bytes(image_bytes, submission.gemini_model)

                    # Use richer verification when available
                    verification_payload = None
                    if verification_service is not None:
                        extracted = {}
                        try:
                            extracted = json.loads(response_text or "{}") if isinstance(response_text, str) else (response_text or {})
                        except Exception:
                            extracted = {}

                        # Normalize extracted keys/values for verification service
                        if isinstance(extracted, dict):
                            if "product_class" in extracted and "product_type" not in extracted:
                                extracted["product_type"] = extracted.get("product_class")
                            # Ensure alcohol_content is numeric if given as string with %
                            ac_val = extracted.get("alcohol_content")
                            if isinstance(ac_val, str):
                                try:
                                    extracted["alcohol_content"] = float(ac_val.replace("%", "").strip())
                                except Exception:
                                    pass
                            # Provide text fallback for gov-warning search
                            if not extracted.get("all_text_found") and isinstance(response_text, str):
                                extracted["all_text_found"] = response_text

                        form_data = {
                            "brand_name": submission.brand_name or submission.company.name,
                            "product_type": submission.product_class_type,
                            "alcohol_content": submission.alcohol_content,
                            "net_contents": submission.net_contents,
                        }
                        try:
                            fields_result = verification_service.compare_fields(form_data, extracted)
                            status, overall_conf = verification_service.get_overall_status(fields_result)
                            verification_payload = {
                                "fields": fields_result,
                                "overall": {"status": status, "confidence": overall_conf},
                            }
                        except Exception:
                            verification_payload = None

                    if verification_payload is None:
                        # Fallback to simple PRD verification
                        expected_brand = submission.brand_name or submission.company.name
                        per_ver = _verify_against_prd(
                            response_text or "",
                            brand_name=expected_brand,
                            product_class_type=submission.product_class_type,
                            alcohol_content=submission.alcohol_content,
                            net_contents=submission.net_contents,
                        )
                        img.gemini_response = {"raw": response_text, "verification": per_ver}
                        per_image_results.append(per_ver)
                    else:
                        fields = verification_payload.get("fields") or {}
                        legacy = _convert_verification_to_legacy(fields, submission)
                        img.gemini_response = {"raw": response_text, "verification": legacy}
                        per_image_results.append(legacy)
                    img.save()
                    try:
                        combined_text += "\n" + (response_text if isinstance(response_text, str) else json.dumps(response_text))
                    except Exception:
                        combined_text += "\n"

                    # Local OCR verification (presence-based using raw OCR text)
                    ocr_text = local_ocr_image_to_text(local_path)
                    ocr_ver = _verify_against_prd(
                        ocr_text or "",
                        brand_name=submission.brand_name or submission.company.name,
                        product_class_type=submission.product_class_type,
                        alcohol_content=submission.alcohol_content,
                        net_contents=submission.net_contents,
                    )
                    # Store alongside Gemini verification for the image
                    img_resp = img.gemini_response or {}
                    img_resp["ocr_verification"] = ocr_ver
                    img.gemini_response = img_resp
                    img.save(update_fields=["gemini_response"])
                    ocr_image_results.append(ocr_ver)
                    per_image_ocr_texts.append({"image_id": img.id, "text": ocr_text or ""})

                # Combined verification: aggregate per-image results
                combined = None
                if per_image_results and isinstance(per_image_results[0], dict) and "brand_name" in per_image_results[0]:
                    combined = {
                        "brand_name": _combine_verification_results(per_image_results, "brand_name", submission),
                        "product_class_type": _combine_verification_results(per_image_results, "product_class_type", submission),
                        "alcohol_content": _combine_verification_results(per_image_results, "alcohol_content", submission),
                        "net_contents": {**_combine_verification_results(per_image_results, "net_contents", submission), "optional": True},
                        "government_warning_present": _combine_verification_results(per_image_results, "government_warning_present", submission),
                    }
                    combined["all_pass"] = all([
                        combined["brand_name"]["match"],
                        combined["product_class_type"]["match"],
                        combined["alcohol_content"]["match"],
                        combined["net_contents"]["match"],
                        combined["government_warning_present"]["match"],
                    ])
                else:
                    # Fallback to simple PRD verification
                    expected_brand = submission.brand_name or submission.company.name
                    combined = _verify_against_prd(
                        combined_text,
                        brand_name=expected_brand,
                        product_class_type=submission.product_class_type,
                        alcohol_content=submission.alcohol_content,
                        net_contents=submission.net_contents,
                    )
                # Build combined OCR verification (legacy shape) across images
                combined_ocr = None
                if ocr_image_results:
                    brand_ok = any(bool((r.get("brand_name") or {}).get("match")) for r in ocr_image_results)
                    class_ok = any(bool((r.get("product_class_type") or {}).get("match")) for r in ocr_image_results)
                    ac_ok = any(bool((r.get("alcohol_content") or {}).get("match")) for r in ocr_image_results)
                    net_ok = any(bool((r.get("net_contents") or {}).get("match")) for r in ocr_image_results)
                    gov_ok = any(bool((r.get("government_warning_present") or {}).get("match")) for r in ocr_image_results)
                    combined_ocr = {
                        "brand_name": {"match": brand_ok},
                        "product_class_type": {"match": class_ok},
                        "alcohol_content": {"match": ac_ok},
                        "net_contents": {"match": net_ok, "optional": True},
                        "government_warning_present": {"match": gov_ok},
                        "all_pass": brand_ok and class_ok and ac_ok and net_ok and gov_ok,
                    }
                submission.gemini_response = {"images": per_image_results}
                submission.verification_result = combined
                # Attach OCR summary alongside for display
                gr = submission.gemini_response or {}
                gr["ocr_images"] = ocr_image_results
                gr["ocr_overall"] = combined_ocr
                submission.gemini_response = gr
                # Persist full OCR extract for the submission
                submission.ocr_extract = {
                    "gemini": {"combined_text": combined_text.strip()},
                    "local_ocr": {"images": per_image_ocr_texts},
                }
                submission.status = Submission.STATUS_PROCESSED
                submission.save()
                messages.success(request, "Submission processed successfully.")
                return redirect("submission_detail", pk=submission.pk)
            except Exception as exc:
                logger.exception("HomeView: submission processing failed: %s", exc)
                submission.status = Submission.STATUS_FAILED
                submission.error_message = str(exc)
                submission.save()
                messages.error(request, f"Submission failed: {exc}")
                return redirect("submission_detail", pk=submission.pk)
        else:
            try:
                logger.warning("HomeView: SubmissionForm invalid: %s", form.errors.as_json())
            except Exception:
                logger.warning("HomeView: SubmissionForm invalid (could not serialize errors)")
            messages.error(request, "Please correct the errors below.")
            return self.render_to_response({"form": form, "recent_submissions": Submission.objects.order_by("-created_at")[:10]})


# Submissions
class SubmissionListView(LoginRequiredMixin, ListView):
    model = Submission
    template_name = "submissions/list.html"
    context_object_name = "submissions"
    paginate_by = 20

    def get_queryset(self):
        return Submission.objects.order_by("-created_at")


class SubmissionDetailView(LoginRequiredMixin, DetailView):
    model = Submission
    template_name = "submissions/detail.html"
    context_object_name = "submission"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submission: Submission = context["submission"]
        # Precompute signed URLs and include per-image verification for display
        images_with_urls = []
        for img in submission.images.all().order_by("id"):
            signed_url = generate_signed_url(img.gcs_uri or "") if getattr(img, "gcs_uri", None) else ""
            images_with_urls.append({
                "id": img.id,
                "image_url": img.image.url if getattr(img, "image", None) else "",
                "gcs_uri": img.gcs_uri,
                "signed_url": signed_url,
                "verification": (img.gemini_response or {}).get("verification") if getattr(img, "gemini_response", None) else None,
                "ocr_verification": (img.gemini_response or {}).get("ocr_verification") if getattr(img, "gemini_response", None) else None,
            })
        context["images_with_urls"] = images_with_urls
        # Add comments and comment form
        context["comments"] = submission.comments.all().order_by("-created_at")
        context["comment_form"] = CommentForm()
        return context


class SubmissionReanalyzeView(LoginRequiredMixin, View):
    def post(self, request, pk: int):
        submission: Submission = get_object_or_404(Submission, pk=pk)
        try:
            submission.status = Submission.STATUS_PENDING
            submission.save(update_fields=["status"])

            per_image_results = []
            ocr_image_results = []
            per_image_ocr_texts = []
            combined_text = ""
            # Re-run Gemini on each stored image
            for img in submission.images.all().order_by("id"):
                local_path = getattr(img.image, "path", None)
                if not local_path or not os.path.exists(local_path):
                    logger.warning("Reanalyze: image missing on disk for image id=%s", img.id)
                    continue
                with open(local_path, "rb") as fh:
                    image_bytes = fh.read()
                response_text = call_gemini_with_image_bytes(image_bytes, submission.gemini_model)
                verification_payload = None
                if verification_service is not None:
                    extracted = {}
                    try:
                        extracted = json.loads(response_text or "{}") if isinstance(response_text, str) else (response_text or {})
                    except Exception:
                        extracted = {}
                
                # Normalize extracted keys/values for verification service
                if isinstance(extracted, dict):
                    if "product_class" in extracted and "product_type" not in extracted:
                        extracted["product_type"] = extracted.get("product_class")
                    ac_val = extracted.get("alcohol_content")
                    if isinstance(ac_val, str):
                        try:
                            extracted["alcohol_content"] = float(ac_val.replace("%", "").strip())
                        except Exception:
                            pass
                    if not extracted.get("all_text_found") and isinstance(response_text, str):
                        extracted["all_text_found"] = response_text
                    form_data = {
                        "brand_name": submission.brand_name or submission.company.name,
                        "product_type": submission.product_class_type,
                        "alcohol_content": submission.alcohol_content,
                        "net_contents": submission.net_contents,
                    }
                    try:
                        fields_result = verification_service.compare_fields(form_data, extracted)
                        status, overall_conf = verification_service.get_overall_status(fields_result)
                        verification_payload = {"fields": fields_result, "overall": {"status": status, "confidence": overall_conf}}
                    except Exception:
                        verification_payload = None

                if verification_payload is None:
                    expected_brand = submission.brand_name or submission.company.name
                    per_ver = _verify_against_prd(
                        response_text or "",
                        brand_name=expected_brand,
                        product_class_type=submission.product_class_type,
                        alcohol_content=submission.alcohol_content,
                        net_contents=submission.net_contents,
                    )
                    img.gemini_response = {"raw": response_text, "verification": per_ver}
                    per_image_results.append(per_ver)
                else:
                    fields = (verification_payload.get("fields") or {})
                    legacy = _convert_verification_to_legacy(fields, submission)
                    img.gemini_response = {"raw": response_text, "verification": legacy}
                    per_image_results.append(legacy)
                # Local OCR per image
                ocr_text = local_ocr_image_to_text(local_path)
                ocr_ver = _verify_against_prd(
                    ocr_text or "",
                    brand_name=submission.brand_name or submission.company.name,
                    product_class_type=submission.product_class_type,
                    alcohol_content=submission.alcohol_content,
                    net_contents=submission.net_contents,
                )
                img_resp = img.gemini_response or {}
                img_resp["ocr_verification"] = ocr_ver
                img.gemini_response = img_resp
                img.save(update_fields=["gemini_response"])
                ocr_image_results.append(ocr_ver)
                per_image_ocr_texts.append({"image_id": img.id, "text": ocr_text or ""})
                try:
                    combined_text += "\n" + (response_text if isinstance(response_text, str) else json.dumps(response_text))
                except Exception:
                    combined_text += "\n"

            combined = None
            if per_image_results and isinstance(per_image_results[0], dict) and "brand_name" in per_image_results[0]:
                combined = {
                    "brand_name": _combine_verification_results(per_image_results, "brand_name", submission),
                    "product_class_type": _combine_verification_results(per_image_results, "product_class_type", submission),
                    "alcohol_content": _combine_verification_results(per_image_results, "alcohol_content", submission),
                    "net_contents": {**_combine_verification_results(per_image_results, "net_contents", submission), "optional": True},
                    "government_warning_present": _combine_verification_results(per_image_results, "government_warning_present", submission),
                }
                combined["all_pass"] = all([
                    combined["brand_name"]["match"],
                    combined["product_class_type"]["match"],
                    combined["alcohol_content"]["match"],
                    combined["net_contents"]["match"],
                    combined["government_warning_present"]["match"],
                ])
            else:
                expected_brand = submission.brand_name or submission.company.name
                combined = _verify_against_prd(
                    combined_text,
                    brand_name=expected_brand,
                    product_class_type=submission.product_class_type,
                    alcohol_content=submission.alcohol_content,
                    net_contents=submission.net_contents,
                )
            # Build OCR combined
            combined_ocr = None
            if ocr_image_results:
                brand_ok = any(bool((r.get("brand_name") or {}).get("match")) for r in ocr_image_results)
                class_ok = any(bool((r.get("product_class_type") or {}).get("match")) for r in ocr_image_results)
                ac_ok = any(bool((r.get("alcohol_content") or {}).get("match")) for r in ocr_image_results)
                net_ok = any(bool((r.get("net_contents") or {}).get("match")) for r in ocr_image_results)
                gov_ok = any(bool((r.get("government_warning_present") or {}).get("match")) for r in ocr_image_results)
                combined_ocr = {
                    "brand_name": {"match": brand_ok},
                    "product_class_type": {"match": class_ok},
                    "alcohol_content": {"match": ac_ok},
                    "net_contents": {"match": net_ok, "optional": True},
                    "government_warning_present": {"match": gov_ok},
                    "all_pass": brand_ok and class_ok and ac_ok and net_ok and gov_ok,
                }

            submission.gemini_response = {"images": per_image_results, "ocr_images": ocr_image_results, "ocr_overall": combined_ocr}
            submission.verification_result = combined
            submission.ocr_extract = {
                "gemini": {"combined_text": combined_text.strip()},
                "local_ocr": {"images": per_image_ocr_texts},
            }
            submission.status = Submission.STATUS_PROCESSED
            submission.save(update_fields=["gemini_response", "verification_result", "status"])
            messages.success(request, "Re-analysis complete.")
        except Exception as exc:
            logger.exception("SubmissionReanalyzeView: failed re-analysis: %s", exc)
            submission.status = Submission.STATUS_FAILED
            submission.error_message = str(exc)
            submission.save(update_fields=["status", "error_message"])
            messages.error(request, f"Re-analysis failed: {exc}")
        return redirect("submission_detail", pk=submission.pk)


class SubmissionCommentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk: int):
        submission: Submission = get_object_or_404(Submission, pk=pk)
        form = CommentForm(request.POST)
        if form.is_valid():
            comment: Comment = form.save(commit=False)
            comment.submission = submission
            comment.user = request.user
            comment.save()
            messages.success(request, "Comment added successfully.")
        else:
            messages.error(request, "Please correct the errors in your comment.")
        return redirect("submission_detail", pk=submission.pk)


class SubmissionImageReanalyzeView(LoginRequiredMixin, View):
    def post(self, request, pk: int, image_id: int):
        submission: Submission = get_object_or_404(Submission, pk=pk)
        img: SubmissionImage = get_object_or_404(SubmissionImage, pk=image_id, submission=submission)
        try:
            # Re-run Gemini for this image
            local_path = getattr(img.image, "path", None)
            if not local_path or not os.path.exists(local_path):
                messages.error(request, "Image file missing on disk.")
                return redirect("submission_detail", pk=submission.pk)
            with open(local_path, "rb") as fh:
                image_bytes = fh.read()
            response_text = call_gemini_with_image_bytes(image_bytes, submission.gemini_model)

            # Normalize extraction
            verification_payload = None
            extracted = {}
            try:
                extracted = json.loads(response_text or "{}") if isinstance(response_text, str) else (response_text or {})
            except Exception:
                extracted = {}
            if isinstance(extracted, dict):
                if "product_class" in extracted and "product_type" not in extracted:
                    extracted["product_type"] = extracted.get("product_class")
                ac_val = extracted.get("alcohol_content")
                if isinstance(ac_val, str):
                    try:
                        extracted["alcohol_content"] = float(ac_val.replace("%", "").strip())
                    except Exception:
                        pass
                if not extracted.get("all_text_found") and isinstance(response_text, str):
                    extracted["all_text_found"] = response_text

            form_data = {
                "brand_name": submission.brand_name or submission.company.name,
                "product_type": submission.product_class_type,
                "alcohol_content": submission.alcohol_content,
                "net_contents": submission.net_contents,
            }
            try:
                fields_result = verification_service.compare_fields(form_data, extracted)
                status, overall_conf = verification_service.get_overall_status(fields_result)
                verification_payload = {"fields": fields_result, "overall": {"status": status, "confidence": overall_conf}}
            except Exception:
                verification_payload = None

            # Map to legacy shape for per-image storage
            if verification_payload is None:
                expected_brand = submission.brand_name or submission.company.name
                legacy = _verify_against_prd(
                    response_text or "",
                    brand_name=expected_brand,
                    product_class_type=submission.product_class_type,
                    alcohol_content=submission.alcohol_content,
                    net_contents=submission.net_contents,
                )
            else:
                fields = (verification_payload.get("fields") or {})
                legacy = _convert_verification_to_legacy(fields, submission)

            # Save per-image result
            img.gemini_response = {"raw": response_text, "verification": legacy}
            # Local OCR on this image
            ocr_text = local_ocr_image_to_text(local_path)
            ocr_ver = _verify_against_prd(
                ocr_text or "",
                brand_name=submission.brand_name or submission.company.name,
                product_class_type=submission.product_class_type,
                alcohol_content=submission.alcohol_content,
                net_contents=submission.net_contents,
            )
            img.gemini_response["ocr_verification"] = ocr_ver
            img.save(update_fields=["gemini_response"])

            # Recompute combined across all images
            per_image_results = []
            ocr_image_results = []
            combined_text = ""
            for im in submission.images.all().order_by("id"):
                vr = (im.gemini_response or {}).get("verification")
                if vr:
                    per_image_results.append(vr)
                ocr_vr = (im.gemini_response or {}).get("ocr_verification")
                if ocr_vr:
                    ocr_image_results.append(ocr_vr)
                raw_part = (im.gemini_response or {}).get("raw")
                try:
                    combined_text += "\n" + (raw_part if isinstance(raw_part, str) else json.dumps(raw_part))
                except Exception:
                    combined_text += "\n"

            if per_image_results and isinstance(per_image_results[0], dict) and "brand_name" in per_image_results[0]:
                combined = {
                    "brand_name": _combine_verification_results(per_image_results, "brand_name", submission),
                    "product_class_type": _combine_verification_results(per_image_results, "product_class_type", submission),
                    "alcohol_content": _combine_verification_results(per_image_results, "alcohol_content", submission),
                    "net_contents": {**_combine_verification_results(per_image_results, "net_contents", submission), "optional": True},
                    "government_warning_present": _combine_verification_results(per_image_results, "government_warning_present", submission),
                }
                combined["all_pass"] = all([
                    combined["brand_name"]["match"],
                    combined["product_class_type"]["match"],
                    combined["alcohol_content"]["match"],
                    combined["net_contents"]["match"],
                    combined["government_warning_present"]["match"],
                ])
            else:
                expected_brand = submission.brand_name or submission.company.name
                combined = _verify_against_prd(
                    combined_text,
                    brand_name=expected_brand,
                    product_class_type=submission.product_class_type,
                    alcohol_content=submission.alcohol_content,
                    net_contents=submission.net_contents,
                )

            # OCR combined
            combined_ocr = None
            if ocr_image_results:
                brand_ok = any(bool((r.get("brand_name") or {}).get("match")) for r in ocr_image_results)
                class_ok = any(bool((r.get("product_class_type") or {}).get("match")) for r in ocr_image_results)
                ac_ok = any(bool((r.get("alcohol_content") or {}).get("match")) for r in ocr_image_results)
                net_ok = any(bool((r.get("net_contents") or {}).get("match")) for r in ocr_image_results)
                gov_ok = any(bool((r.get("government_warning_present") or {}).get("match")) for r in ocr_image_results)
                combined_ocr = {
                    "brand_name": {"match": brand_ok},
                    "product_class_type": {"match": class_ok},
                    "alcohol_content": {"match": ac_ok},
                    "net_contents": {"match": net_ok, "optional": True},
                    "government_warning_present": {"match": gov_ok},
                    "all_pass": brand_ok and class_ok and ac_ok and net_ok and gov_ok,
                }

            submission.gemini_response = {"images": per_image_results, "ocr_images": ocr_image_results, "ocr_overall": combined_ocr}
            submission.verification_result = combined
            submission.save(update_fields=["gemini_response", "verification_result"])
            messages.success(request, "Image re-analyzed.")
        except Exception as exc:
            logger.exception("SubmissionImageReanalyzeView: failed re-analysis: %s", exc)
            submission.status = Submission.STATUS_FAILED
            submission.error_message = str(exc)
            submission.save(update_fields=["status", "error_message"])
            messages.error(request, f"Re-analysis failed: {exc}")
        return redirect("submission_detail", pk=submission.pk)

class SubmissionCreateView(LoginRequiredMixin, CreateView):
    model = Submission
    form_class = SubmissionForm
    template_name = "submissions/form.html"

    def form_invalid(self, form):
        try:
            logger.warning("SubmissionCreateView: form invalid: %s", form.errors.as_json())
        except Exception:
            logger.warning("SubmissionCreateView: form invalid (could not serialize errors)")
        messages.error(self.request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        self.object: Submission = form.save(commit=False)
        self.object.user = self.request.user
        self.object.status = Submission.STATUS_PENDING
        self.object.save()
        try:
            front = self.request.FILES.get("front_image")
            back = self.request.FILES.get("back_image")
            logger.info("SubmissionCreateView: received front=%s back=%s", bool(front), bool(back))
            if not front and not back:
                messages.error(self.request, "Please add at least one image.")
                logger.warning("SubmissionCreateView: no image files submitted")
                return redirect("submission_detail", pk=self.object.pk)
            per_image_results = []
            combined_text = ""
            for f in [front, back]:
                if not f:
                    continue
                img = SubmissionImage.objects.create(submission=self.object, image=f)
                local_path = img.image.path
                filename = os.path.basename(local_path)
                gcs_path = f"submissions/{self.object.id}/{filename}"
                gs_uri, _ = upload_file_to_gcs(local_path, gcs_path)
                img.gcs_uri = gs_uri
                with open(local_path, "rb") as fh:
                    image_bytes = fh.read()
                response_text = call_gemini_with_image_bytes(image_bytes, self.object.gemini_model)

                verification_payload = None
                if verification_service is not None:
                    extracted = {}
                    try:
                        extracted = json.loads(response_text or "{}") if isinstance(response_text, str) else (response_text or {})
                    except Exception:
                        extracted = {}
                
                # Normalize extracted keys/values for verification service
                if isinstance(extracted, dict):
                    if "product_class" in extracted and "product_type" not in extracted:
                        extracted["product_type"] = extracted.get("product_class")
                    ac_val = extracted.get("alcohol_content")
                    if isinstance(ac_val, str):
                        try:
                            extracted["alcohol_content"] = float(ac_val.replace("%", "").strip())
                        except Exception:
                            pass
                    if not extracted.get("all_text_found") and isinstance(response_text, str):
                        extracted["all_text_found"] = response_text
                    form_data = {
                        "brand_name": self.object.brand_name or self.object.company.name,
                        "product_type": self.object.product_class_type,
                        "alcohol_content": self.object.alcohol_content,
                        "net_contents": self.object.net_contents,
                    }
                    try:
                        fields_result = verification_service.compare_fields(form_data, extracted)
                        status, overall_conf = verification_service.get_overall_status(fields_result)
                        verification_payload = {"fields": fields_result, "overall": {"status": status, "confidence": overall_conf}}
                    except Exception:
                        verification_payload = None

                if verification_payload is None:
                    expected_brand = self.object.brand_name or self.object.company.name
                    per_ver = _verify_against_prd(
                        response_text or "",
                        brand_name=expected_brand,
                        product_class_type=self.object.product_class_type,
                        alcohol_content=self.object.alcohol_content,
                        net_contents=self.object.net_contents,
                    )
                    img.gemini_response = {"raw": response_text, "verification": per_ver}
                    per_image_results.append(per_ver)
                else:
                    fields = (verification_payload.get("fields") or {})
                    legacy = _convert_verification_to_legacy(fields, self.object)
                    img.gemini_response = {"raw": response_text, "verification": legacy}
                    per_image_results.append(legacy)
                img.save()
                try:
                    combined_text += "\n" + (response_text if isinstance(response_text, str) else json.dumps(response_text))
                except Exception:
                    combined_text += "\n"

            combined = None
            if per_image_results and isinstance(per_image_results[0], dict) and "brand_name" in per_image_results[0]:
                combined = {
                    "brand_name": _combine_verification_results(per_image_results, "brand_name", self.object),
                    "product_class_type": _combine_verification_results(per_image_results, "product_class_type", self.object),
                    "alcohol_content": _combine_verification_results(per_image_results, "alcohol_content", self.object),
                    "net_contents": {**_combine_verification_results(per_image_results, "net_contents", self.object), "optional": True},
                    "government_warning_present": _combine_verification_results(per_image_results, "government_warning_present", self.object),
                }
                combined["all_pass"] = all([
                    combined["brand_name"]["match"],
                    combined["product_class_type"]["match"],
                    combined["alcohol_content"]["match"],
                    combined["net_contents"]["match"],
                    combined["government_warning_present"]["match"],
                ])
            else:
                expected_brand = self.object.brand_name or self.object.company.name
                combined = _verify_against_prd(
                    combined_text,
                    brand_name=expected_brand,
                    product_class_type=self.object.product_class_type,
                    alcohol_content=self.object.alcohol_content,
                    net_contents=self.object.net_contents,
                )

            self.object.gemini_response = {"images": per_image_results}
            self.object.verification_result = combined
            self.object.status = Submission.STATUS_PROCESSED
            self.object.save()
            messages.success(self.request, "Submission processed successfully.")
        except Exception as exc:
            logger.exception("SubmissionCreateView: submission processing failed: %s", exc)
            self.object.status = Submission.STATUS_FAILED
            self.object.error_message = str(exc)
            self.object.save()
            messages.error(self.request, f"Submission failed: {exc}")
        return redirect("submission_detail", pk=self.object.pk)


def _normalize_text(text: str) -> str:
    return (text or "").lower()


def _verify_against_prd(extracted_text: str, *, brand_name: str, product_class_type: str, alcohol_content: str, net_contents: str):
    import re
    text = _normalize_text(extracted_text)
    brand_ok = _normalize_text(brand_name) in text if brand_name else False
    class_ok = _normalize_text(product_class_type) in text if product_class_type else False
    # Alcohol content: exact numeric match (ignoring additional decimal places)
    ac = (alcohol_content or "").strip()
    ac_ok = False
    try:
        if ac:
            # expected numeric value without % sign
            exp = _normalize_text(ac).replace("%", "").strip()
            expected_val = float(exp)
            # find all numbers followed by optional space and % in the text
            for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
                try:
                    found_val = float(m.group(1))
                except Exception:
                    continue
                if abs(found_val - expected_val) <= 0.0:
                    ac_ok = True
                    break
    except Exception:
        ac_ok = False
    net_ok = _normalize_text(net_contents) in text if net_contents else True  # optional
    gov_warn_ok = "government warning" in text
    all_ok = brand_ok and class_ok and ac_ok and net_ok and gov_warn_ok
    return {
        "brand_name": {"expected": brand_name, "match": brand_ok},
        "product_class_type": {"expected": product_class_type, "match": class_ok},
        "alcohol_content": {"expected": alcohol_content, "match": ac_ok},
        "net_contents": {"expected": net_contents, "match": net_ok, "optional": True},
        "government_warning_present": {"expected": True, "match": gov_warn_ok},
        "all_pass": all_ok,
    }


# Companies
class CompanyListView(LoginRequiredMixin, ListView):
    model = Company
    template_name = "companies/list.html"
    context_object_name = "companies"
    paginate_by = 20


class CompanyDetailView(LoginRequiredMixin, DetailView):
    model = Company
    template_name = "companies/detail.html"
    context_object_name = "company"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company: Company = context["company"]
        context["submissions"] = Submission.objects.filter(company=company).order_by("-created_at")
        return context


class CompanyCreateView(LoginRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = "companies/form.html"
    success_url = reverse_lazy("company_list")


class CompanyUpdateView(LoginRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = "companies/form.html"
    success_url = reverse_lazy("company_list")


# Locations (nested under company)
class LocationListView(LoginRequiredMixin, ListView):
    model = Location
    template_name = "locations/list.html"
    context_object_name = "locations"
    paginate_by = 20

    def get_queryset(self):
        self.company = get_object_or_404(Company, pk=self.kwargs["company_id"])
        return self.company.locations.all().order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["company"] = get_object_or_404(Company, pk=self.kwargs["company_id"])
        return context


class LocationDetailView(LoginRequiredMixin, DetailView):
    model = Location
    template_name = "locations/detail.html"
    context_object_name = "location"

    def get_queryset(self):
        return Location.objects.filter(company_id=self.kwargs["company_id"])  

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["company"] = get_object_or_404(Company, pk=self.kwargs["company_id"])
        return context


class LocationCreateView(LoginRequiredMixin, CreateView):
    model = Location
    form_class = LocationForm
    template_name = "locations/form.html"

    def form_valid(self, form):
        company = get_object_or_404(Company, pk=self.kwargs["company_id"])
        self.object = form.save(commit=False)
        self.object.company = company
        self.object.save()
        messages.success(self.request, "Location created.")
        return redirect("location_list", company_id=company.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["company"] = get_object_or_404(Company, pk=self.kwargs["company_id"])
        return context


class LocationUpdateView(LoginRequiredMixin, UpdateView):
    model = Location
    form_class = LocationForm
    template_name = "locations/form.html"

    def get_queryset(self):
        return Location.objects.filter(company_id=self.kwargs["company_id"])  

    def get_success_url(self):
        return reverse("location_list", kwargs={"company_id": self.kwargs["company_id"]})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["company"] = get_object_or_404(Company, pk=self.kwargs["company_id"])
        return context


class LocationDeleteView(LoginRequiredMixin, DeleteView):
    model = Location
    template_name = "locations/confirm_delete.html"

    def get_queryset(self):
        return Location.objects.filter(company_id=self.kwargs["company_id"])  

    def get_success_url(self):
        return reverse("location_list", kwargs={"company_id": self.kwargs["company_id"]})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["company"] = get_object_or_404(Company, pk=self.kwargs["company_id"])
        return context


class CompanyLocationsApiView(LoginRequiredMixin, View):
    def get(self, request, company_id: int):
        locations = Location.objects.filter(company_id=company_id).order_by("name").values("id", "name")
        return JsonResponse({"locations": list(locations)})


