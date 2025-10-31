from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Company, Location, Submission, Comment

# Shared Tailwind input classes for consistent styling across forms
BASE_INPUT_CLASSES = (
    "bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg "
    "focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 "
    "dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white "
    "dark:focus:ring-blue-500 dark:focus:border-blue-500"
)


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES, "placeholder": "Company name"}),
            "description": forms.Textarea(attrs={"class": BASE_INPUT_CLASSES, "rows": 3, "placeholder": "Brief description"}),
        }


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = [
            "name",
            "city",
            "state",
            "country",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES, "placeholder": "Location name"}),
            "city": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES}),
            "state": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES}),
            # country widget set in __init__ to inject ordered choices
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_countries = [
            "Argentina","Australia","Austria","Belgium","Brazil","Canada","Chile","China",
            "Colombia","Czech Republic","Denmark","Finland","France","Germany","Greece","Hong Kong",
            "Iceland","India","Ireland","Israel","Italy","Japan","Luxembourg","Mexico","Netherlands",
            "New Zealand","Norway","Poland","Portugal","Singapore","South Africa","South Korea","Spain",
            "Sweden","Switzerland","Taiwan","Thailand","Turkey","United Kingdom","United States","Vietnam"
        ]
        countries_sorted = sorted({c for c in base_countries if c != "United States"})
        # Ensure current value (e.g., when editing) is preserved even if not in our list
        current_value = self.instance.country if getattr(self, "instance", None) else None
        if current_value and current_value not in countries_sorted and current_value != "United States":
            countries_sorted.append(current_value)
            countries_sorted = sorted(countries_sorted)
        choices = [("", "Select a country")] + [("United States", "United States")] + [(c, c) for c in countries_sorted]
        initial_country = current_value if current_value in dict(choices) else ""
        self.fields["country"] = forms.ChoiceField(
            choices=choices,
            required=False,
            initial=initial_country,
            widget=forms.Select(attrs={"class": BASE_INPUT_CLASSES}),
        )


class SubmissionForm(forms.ModelForm):
    front_image = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": BASE_INPUT_CLASSES, "accept": "image/*"}),
        required=True,
    )
    back_image = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": BASE_INPUT_CLASSES, "accept": "image/*"}),
        required=False,
    )

    # Accept alcohol content as a float (e.g., 13.5) while storing as string in model
    alcohol_content = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASSES, "step": "0.1", "min": "0", "placeholder": "e.g. 13.5"}),
        required=True,
    )

    class Meta:
        model = Submission
        fields = [
            "company",
            "brand_name",
            "product_class_type",
            "alcohol_content",
            "net_contents",
        ]
        widgets = {
            "company": forms.Select(attrs={"class": BASE_INPUT_CLASSES}),
            # Optional override to company name if different
            "brand_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES, "placeholder": "Optional: brand name override"}),
            "product_class_type": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES, "placeholder": "e.g. Beer, Wine"}),
            "alcohol_content": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES, "placeholder": "e.g. 12%"}),
            "net_contents": forms.TextInput(attrs={"class": BASE_INPUT_CLASSES, "placeholder": "e.g. 750 mL"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make brand_name optional in the form as it overrides company name when provided
        self.fields["brand_name"].required = False



class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={"class": BASE_INPUT_CLASSES, "rows": 3, "placeholder": "Add a comment..."}),
        }


class TailwindAuthenticationForm(AuthenticationForm):
    """Authentication form that applies Tailwind classes to inputs."""

    INPUT_CLASSES = (
        "shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 "
        "leading-tight focus:outline-none focus:shadow-outline"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "").strip()
            field.widget.attrs["class"] = f"{existing} {self.INPUT_CLASSES}".strip()

