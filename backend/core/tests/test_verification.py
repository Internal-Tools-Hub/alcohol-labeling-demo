from django.test import SimpleTestCase

from core.views import _verify_against_prd


class VerifyAgainstPrdTests(SimpleTestCase):
    def test_all_fields_match_passes(self):
        extracted = (
            "Old Tom Distillery\nKentucky Straight Bourbon Whiskey\nAlc. 45% by Vol.\n"
            "750 mL\nGOVERNMENT WARNING: ..."
        )
        result = _verify_against_prd(
            extracted_text=extracted,
            brand_name="Old Tom Distillery",
            product_class_type="Kentucky Straight Bourbon Whiskey",
            alcohol_content="45%",
            net_contents="750 mL",
        )
        assert result["brand_name"]["match"] is True
        assert result["product_class_type"]["match"] is True
        assert result["alcohol_content"]["match"] is True
        assert result["net_contents"]["match"] is True
        assert result["government_warning_present"]["match"] is True
        assert result["all_pass"] is True

    def test_missing_government_warning_fails_overall(self):
        extracted = (
            "Old Tom Distillery\nKentucky Straight Bourbon Whiskey\nAlc. 45% by Vol.\n750 mL"
        )
        result = _verify_against_prd(
            extracted_text=extracted,
            brand_name="Old Tom Distillery",
            product_class_type="Kentucky Straight Bourbon Whiskey",
            alcohol_content="45%",
            net_contents="750 mL",
        )
        assert result["government_warning_present"]["match"] is False
        assert result["all_pass"] is False

    def test_net_contents_optional(self):
        extracted = (
            "Old Tom Distillery\nVodka\nAlc. 40% by Vol.\nGOVERNMENT WARNING"
        )
        result = _verify_against_prd(
            extracted_text=extracted,
            brand_name="Old Tom Distillery",
            product_class_type="Vodka",
            alcohol_content="40%",
            net_contents="",
        )
        # net_contents optional -> overall can still pass
        assert result["brand_name"]["match"] is True
        assert result["product_class_type"]["match"] is True
        assert result["alcohol_content"]["match"] is True
        assert result["net_contents"]["match"] is True  # treated as True when not provided
        assert result["government_warning_present"]["match"] is True
        assert result["all_pass"] is True

    def test_alcohol_content_spacing_variation(self):
        # Allow a space before % per simple normalization
        extracted = "Alc 45 % by Vol. GOVERNMENT WARNING Brand X Bourbon"
        result = _verify_against_prd(
            extracted_text=extracted,
            brand_name="Brand X",
            product_class_type="Bourbon",
            alcohol_content="45%",
            net_contents="",
        )
        assert result["alcohol_content"]["match"] is True
        assert result["all_pass"] is True


