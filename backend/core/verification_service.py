import re
from fuzzywuzzy import fuzz
from typing import Dict, Any, List, Tuple


class VerificationService:
    def __init__(self):
        """Initialize verification service with matching rules"""
        self.matching_rules = {
            'brand_name': {
                'similarity_threshold': 85,
                'case_sensitive': False,
                'normalize': True
            },
            'product_type': {
                'similarity_threshold': 70,
                'case_sensitive': False,
                'normalize': True
            },
            'alcohol_content': {
                'tolerance': 0.0,  # exact match required
                'exact_match': True
            },
            'net_contents': {
                'exact_match': True,
                'normalize_units': True
            },
            'government_warning': {
                'substring_match': True,
                'required_text': 'GOVERNMENT WARNING'
            }
        }

    def compare_fields(self, form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Compare form data with extracted data and return detailed results
        """
        results = {}
        for field_name in ['brand_name', 'product_type', 'alcohol_content', 'net_contents']:
            if field_name in form_data and field_name in extracted_data:
                results[field_name] = self._compare_field(
                    field_name,
                    form_data[field_name],
                    extracted_data[field_name]
                )
        results['government_warning'] = self._check_government_warning(extracted_data)
        return results

    def _compare_field(self, field_name: str, expected: Any, extracted: Any) -> Dict[str, Any]:
        if expected is None or extracted is None:
            return {
                'expected': expected,
                'extracted': extracted,
                'matched': False,
                'confidence': 0.0,
                'details': 'Missing data in form or extraction'
            }
        rules = self.matching_rules.get(field_name, {})
        if field_name == 'brand_name':
            return self._compare_brand_name(expected, extracted, rules)
        elif field_name == 'product_type':
            return self._compare_product_type(expected, extracted, rules)
        elif field_name == 'alcohol_content':
            return self._compare_alcohol_content(expected, extracted, rules)
        elif field_name == 'net_contents':
            return self._compare_net_contents(expected, extracted, rules)
        else:
            return self._compare_generic(expected, extracted, rules)

    def _compare_brand_name(self, expected: str, extracted: str, rules: Dict) -> Dict[str, Any]:
        if not expected or not extracted:
            return {
                'expected': expected,
                'extracted': extracted,
                'matched': False,
                'confidence': 0.0,
                'details': 'Missing brand name data'
            }
        expected_norm = self._normalize_text(expected) if rules.get('normalize') else expected
        extracted_norm = self._normalize_text(extracted) if rules.get('normalize') else extracted
        similarity = fuzz.ratio(expected_norm, extracted_norm)
        threshold = rules.get('similarity_threshold', 85)
        matched = similarity >= threshold
        return {
            'expected': expected,
            'extracted': extracted,
            'matched': matched,
            'confidence': similarity / 100.0,
            'details': f"Similarity: {similarity}% (threshold: {threshold}%)"
        }

    def _compare_product_type(self, expected: str, extracted: str, rules: Dict) -> Dict[str, Any]:
        if not expected or not extracted:
            return {
                'expected': expected,
                'extracted': extracted,
                'matched': False,
                'confidence': 0.0,
                'details': 'Missing product type data'
            }
        expected_norm = self._normalize_text(expected) if rules.get('normalize') else expected
        extracted_norm = self._normalize_text(extracted) if rules.get('normalize') else extracted
        similarity = fuzz.ratio(expected_norm, extracted_norm)
        threshold = rules.get('similarity_threshold', 80)
        matched = similarity >= threshold
        return {
            'expected': expected,
            'extracted': extracted,
            'matched': matched,
            'confidence': similarity / 100.0,
            'details': f"Similarity: {similarity}% (threshold: {threshold}%)"
        }

    def _compare_alcohol_content(self, expected: float, extracted: Any, rules: Dict) -> Dict[str, Any]:
        try:
            expected_val = float(expected)
            extracted_val = float(extracted)
        except (ValueError, TypeError):
            return {
                'expected': expected,
                'extracted': extracted,
                'matched': False,
                'confidence': 0.0,
                'details': 'Invalid alcohol content values'
            }
        tolerance = rules.get('tolerance', 0.0)
        difference = abs(expected_val - extracted_val)
        matched = difference <= tolerance
        return {
            'expected': expected_val,
            'extracted': extracted_val,
            'matched': matched,
            'confidence': 1.0 - (difference / max(expected_val, extracted_val, 1.0)),
            'details': f"Difference: {difference:.2f}% (tolerance: ±{tolerance}%)"
        }

    def _compare_net_contents(self, expected: str, extracted: str, rules: Dict) -> Dict[str, Any]:
        if not expected or not extracted:
            return {
                'expected': expected,
                'extracted': extracted,
                'matched': False,
                'confidence': 0.0,
                'details': 'Missing net contents data'
            }
        expected_norm = self._normalize_net_contents(expected)
        extracted_norm = self._normalize_net_contents(extracted)
        matched = expected_norm == extracted_norm
        return {
            'expected': expected,
            'extracted': extracted,
            'matched': matched,
            'confidence': 1.0 if matched else 0.0,
            'details': f"Normalized: '{expected_norm}' vs '{extracted_norm}'"
        }

    def _check_government_warning(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        all_text = extracted_data.get('all_text_found', '')
        warning_present = extracted_data.get('government_warning_present', False)
        required_text = self.matching_rules['government_warning']['required_text']
        text_found = required_text.upper() in all_text.upper()
        matched = warning_present or text_found
        return {
            'expected': 'Present',
            'extracted': 'Present' if matched else 'Missing',
            'matched': matched,
            'confidence': 1.0 if matched else 0.0,
            'details': f"Government warning {'found' if matched else 'not found'} in label text"
        }

    def _compare_generic(self, expected: Any, extracted: Any, rules: Dict) -> Dict[str, Any]:
        if rules.get('case_sensitive', True):
            matched = str(expected) == str(extracted)
        else:
            matched = str(expected).lower() == str(extracted).lower()
        return {
            'expected': expected,
            'extracted': extracted,
            'matched': matched,
            'confidence': 1.0 if matched else 0.0,
            'details': 'Exact match' if matched else 'Values do not match'
        }

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        normalized = text.lower()
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        normalized = re.sub(r'[.,;:!?]', '', normalized)
        return normalized

    def _normalize_net_contents(self, contents: str) -> str:
        if not contents:
            return ""
        normalized = contents.lower().strip()
        unit_mappings = {
            'ml': 'ml',
            'milliliter': 'ml',
            'milliliters': 'ml',
            'l': 'l',
            'liter': 'l',
            'liters': 'l',
            'liter': 'l',
            'fl oz': 'fl oz',
            'fluid ounce': 'fl oz',
            'fluid ounces': 'fl oz',
            'oz': 'oz',
            'ounce': 'oz',
            'ounces': 'oz'
        }
        match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zA-Z\s]+)', normalized)
        if match:
            number = match.group(1)
            unit = match.group(2).strip()
            normalized_unit = unit_mappings.get(unit, unit)
            return f"{number} {normalized_unit}"
        return normalized

    def get_overall_status(self, results: Dict[str, Dict[str, Any]]) -> Tuple[str, float]:
        if not results:
            return 'error', 0.0
        total_fields = len(results)
        matched_fields = sum(1 for result in results.values() if result.get('matched', False))
        confidences = [result.get('confidence', 0.0) for result in results.values()]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        if matched_fields == total_fields:
            return 'matched', overall_confidence
        elif matched_fields > 0:
            return 'partial', overall_confidence
        else:
            return 'mismatched', overall_confidence


# Global verification service instance
verification_service = VerificationService()


