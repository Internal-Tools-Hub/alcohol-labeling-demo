import os
import logging
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView, View

from .forms import CompanyForm, LocationForm, SubmissionForm
from .models import Company, Location, Submission, SubmissionImage
from .services import upload_file_to_gcs, call_gemini_with_image_bytes, generate_signed_url

logger = logging.getLogger(__name__)


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
                    # Per-image verification against PRD
                    expected_brand = submission.brand_name or submission.company.name
                    per_ver = _verify_against_prd(
                        response_text or "",
                        brand_name=expected_brand,
                        product_class_type=submission.product_class_type,
                        alcohol_content=submission.alcohol_content,
                        net_contents=submission.net_contents,
                    )
                    img.gemini_response = {"raw": response_text, "verification": per_ver}
                    img.save()
                    per_image_results.append(per_ver)
                    combined_text += "\n" + (response_text or "")

                # Verification per PRD + distilled spirits checklist highlights
                expected_brand = submission.brand_name or submission.company.name
                combined = _verify_against_prd(
                    combined_text,
                    brand_name=expected_brand,
                    product_class_type=submission.product_class_type,
                    alcohol_content=submission.alcohol_content,
                    net_contents=submission.net_contents,
                )
                submission.gemini_response = {"images": per_image_results}
                submission.verification_result = combined
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
            })
        context["images_with_urls"] = images_with_urls
        return context


class SubmissionReanalyzeView(LoginRequiredMixin, View):
    def post(self, request, pk: int):
        submission: Submission = get_object_or_404(Submission, pk=pk)
        try:
            submission.status = Submission.STATUS_PENDING
            submission.save(update_fields=["status"])

            per_image_results = []
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
                expected_brand = submission.brand_name or submission.company.name
                per_ver = _verify_against_prd(
                    response_text or "",
                    brand_name=expected_brand,
                    product_class_type=submission.product_class_type,
                    alcohol_content=submission.alcohol_content,
                    net_contents=submission.net_contents,
                )
                img.gemini_response = {"raw": response_text, "verification": per_ver}
                img.save(update_fields=["gemini_response"])
                per_image_results.append(per_ver)
                combined_text += "\n" + (response_text or "")

            expected_brand = submission.brand_name or submission.company.name
            combined = _verify_against_prd(
                combined_text,
                brand_name=expected_brand,
                product_class_type=submission.product_class_type,
                alcohol_content=submission.alcohol_content,
                net_contents=submission.net_contents,
            )
            submission.gemini_response = {"images": per_image_results}
            submission.verification_result = combined
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
                expected_brand = self.object.brand_name or self.object.company.name
                per_ver = _verify_against_prd(
                    response_text or "",
                    brand_name=expected_brand,
                    product_class_type=self.object.product_class_type,
                    alcohol_content=self.object.alcohol_content,
                    net_contents=self.object.net_contents,
                )
                img.gemini_response = {"raw": response_text, "verification": per_ver}
                img.save()
                per_image_results.append(per_ver)
                combined_text += "\n" + (response_text or "")

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
    text = _normalize_text(extracted_text)
    brand_ok = _normalize_text(brand_name) in text if brand_name else False
    class_ok = _normalize_text(product_class_type) in text if product_class_type else False
    # Alcohol content: accept "45%" or number with optional spaces
    ac = (alcohol_content or "").strip()
    ac_ok = False
    if ac:
        ac_lower = _normalize_text(ac)
        ac_ok = ac_lower in text
        if not ac_ok and ac_lower.endswith("%"):
            alt = ac_lower.replace("%", " %")
            ac_ok = alt in text
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


