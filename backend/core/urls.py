from django.urls import path
from . import views


urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),

    path("submissions/", views.SubmissionListView.as_view(), name="submission_list"),
    path("submissions/create/", views.SubmissionCreateView.as_view(), name="submission_create"),
    path("submissions/<int:pk>/", views.SubmissionDetailView.as_view(), name="submission_detail"),
    path("submissions/<int:pk>/reanalyze/", views.SubmissionReanalyzeView.as_view(), name="submission_reanalyze"),

    path("companies/", views.CompanyListView.as_view(), name="company_list"),
    path("companies/create/", views.CompanyCreateView.as_view(), name="company_create"),
    path("companies/<int:pk>/", views.CompanyDetailView.as_view(), name="company_detail"),
    path("companies/<int:pk>/update/", views.CompanyUpdateView.as_view(), name="company_update"),

    path("companies/<int:company_id>/locations/", views.LocationListView.as_view(), name="location_list"),
    path("companies/<int:company_id>/locations/create/", views.LocationCreateView.as_view(), name="location_create"),
    path("companies/<int:company_id>/locations/<int:pk>/", views.LocationDetailView.as_view(), name="location_detail"),
    path("companies/<int:company_id>/locations/<int:pk>/update/", views.LocationUpdateView.as_view(), name="location_update"),
    path("companies/<int:company_id>/locations/<int:pk>/delete/", views.LocationDeleteView.as_view(), name="location_delete"),

    # JSON API
    path("api/companies/<int:company_id>/locations/", views.CompanyLocationsApiView.as_view(), name="api_company_locations"),
]


