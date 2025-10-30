from django.test import TestCase
from django.contrib.auth import get_user_model

from core.models import Company, Location, Submission, SubmissionImage


class ModelBasicsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="u", password="p")
        self.company = Company.objects.create(name="Co A")
        self.location = Location.objects.create(company=self.company, name="Plant 1")

    def test_submission_and_image_str(self):
        s = Submission.objects.create(
            user=self.user,
            company=self.company,
            location=self.location,
            brand_name="Brand A",
            product_class_type="Vodka",
            alcohol_content="40%",
            net_contents="750 mL",
        )
        text = str(s)
        assert "Submission" in text and "Co A" in text

        # Image requires an actual file path to save; just verify the str formatting without file
        img = SubmissionImage.objects.create(submission=s, image="uploads/submissions/dummy.jpg")
        assert f"{s.id}" in str(img)


