import json
import base64
import io
from google import genai
from google.genai import types
from config import Config
import streamlit as st

class GeminiService:
    def __init__(self):
        """Initialize Gemini client"""
        try:
            # Initialize client with API key (google-genai SDK)
            self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
            self.model = "gemini-2.5-flash"  # Using the recommended model
        except Exception as e:
            st.error(f"Failed to initialize Gemini client: {e}")
            raise
    
    def extract_label_text(self, image_bytes, content_type='image/jpeg'):
        """
        Extract structured text from alcohol label image using Gemini Vision API
        
        Args:
            image_bytes: Image data as bytes
            content_type: MIME type of the image
            
        Returns:
            dict: Structured extraction results
        """
        try:
            # Create the prompt for structured extraction
            prompt = """
            Analyze this alcohol beverage label image and extract the following information in JSON format:
            {
              "brand_name": "exact brand name as shown on the label",
              "product_type": "type/class of beverage (e.g., Kentucky Straight Bourbon Whiskey, IPA, Chardonnay)",
              "alcohol_content": "ABV percentage as a number (e.g., 45.0 for 45%)",
              "net_contents": "volume with units (e.g., 750 mL, 12 fl oz, 750ml)",
              "government_warning_present": true/false,
              "all_text_found": "complete OCR text found on the label for reference",
              "confidence": "overall confidence score 0-1"
            }
            
            Important extraction guidelines:
            - Extract brand name exactly as it appears (case-sensitive)
            - For product type, include the full designation (e.g., "Kentucky Straight Bourbon Whiskey" not just "Bourbon")
            - For alcohol content, extract only the numeric value (e.g., 45.0 for "45% Alc./Vol.")
            - For net contents, preserve the exact format including units
            - Check for "GOVERNMENT WARNING" text anywhere on the label
            - If any field cannot be found, use null
            - Provide a confidence score based on text clarity and completeness
            """
            
            # Create the image part
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=content_type,
            )
            
            # Generate content with Gemini
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image_part],
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Low temperature for consistent extraction
                    max_output_tokens=1000
                )
            )
            
            # Parse the JSON response
            extracted_data = self._parse_gemini_response(response.text)
            
            return extracted_data
            
        except Exception as e:
            st.error(f"Failed to extract text from image: {e}")
            return {
                "brand_name": None,
                "product_type": None,
                "alcohol_content": None,
                "net_contents": None,
                "government_warning_present": False,
                "all_text_found": "",
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _parse_gemini_response(self, response_text):
        """Parse Gemini response and extract JSON data"""
        try:
            # Clean the response text
            cleaned_text = response_text.strip()
            
            # Try to find JSON in the response
            if "```json" in cleaned_text:
                # Extract JSON from code block
                json_start = cleaned_text.find("```json") + 7
                json_end = cleaned_text.find("```", json_start)
                if json_end != -1:
                    json_text = cleaned_text[json_start:json_end].strip()
                else:
                    json_text = cleaned_text[json_start:].strip()
            elif "{" in cleaned_text and "}" in cleaned_text:
                # Find JSON object in the text
                json_start = cleaned_text.find("{")
                json_end = cleaned_text.rfind("}") + 1
                json_text = cleaned_text[json_start:json_end]
            else:
                # Fallback: try to parse the entire response
                json_text = cleaned_text
            
            # Parse JSON
            data = json.loads(json_text)
            
            # Validate and clean the data
            return self._validate_extraction_data(data)
            
        except json.JSONDecodeError as e:
            st.warning(f"Failed to parse JSON from Gemini response: {e}")
            # Return fallback data
            return {
                "brand_name": None,
                "product_type": None,
                "alcohol_content": None,
                "net_contents": None,
                "government_warning_present": False,
                "all_text_found": response_text,
                "confidence": 0.0,
                "parse_error": str(e)
            }
        except Exception as e:
            st.error(f"Unexpected error parsing Gemini response: {e}")
            return {
                "brand_name": None,
                "product_type": None,
                "alcohol_content": None,
                "net_contents": None,
                "government_warning_present": False,
                "all_text_found": response_text,
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _validate_extraction_data(self, data):
        """Validate and clean extracted data"""
        validated = {
            "brand_name": data.get("brand_name"),
            "product_type": data.get("product_type"),
            "alcohol_content": data.get("alcohol_content"),
            "net_contents": data.get("net_contents"),
            "government_warning_present": bool(data.get("government_warning_present", False)),
            "all_text_found": data.get("all_text_found", ""),
            "confidence": float(data.get("confidence", 0.0))
        }
        
        # Clean string fields
        for field in ["brand_name", "product_type", "net_contents", "all_text_found"]:
            if validated[field] and isinstance(validated[field], str):
                validated[field] = validated[field].strip()
                if not validated[field]:
                    validated[field] = None
        
        # Validate alcohol content
        if validated["alcohol_content"] is not None:
            try:
                validated["alcohol_content"] = float(validated["alcohol_content"])
                if validated["alcohol_content"] < 0 or validated["alcohol_content"] > 100:
                    validated["alcohol_content"] = None
            except (ValueError, TypeError):
                validated["alcohol_content"] = None
        
        # Ensure confidence is between 0 and 1
        validated["confidence"] = max(0.0, min(1.0, validated["confidence"]))
        
        return validated
    
    def test_connection(self):
        """Test Gemini API connection"""
        try:
            # Simple test with a minimal prompt
            response = self.client.models.generate_content(
                model=self.model,
                contents=["Test connection"],
                config=types.GenerateContentConfig(max_output_tokens=10)
            )
            return True
        except Exception as e:
            st.error(f"Gemini connection test failed: {e}")
            return False

# Global Gemini service instance
gemini_service = GeminiService()

