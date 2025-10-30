from django.contrib import admin
from .models import Company, Location, Submission


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "city", "state")
    search_fields = ("name", "city", "state")
    list_filter = ("company",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "location", "status", "created_at")
    list_filter = ("status", "company")
    search_fields = ("id", "company__name", "location__name")


