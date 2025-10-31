import argparse
import yaml
import os
from pathlib import Path
from google import genai
from google.genai import types
from PIL import Image, ImageChops
from io import BytesIO
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('.env')

def get_client():
    """Get Google AI client with API key from environment"""
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required")
    return genai.Client(api_key=api_key)

def load_data_yaml(category):
    """Load data from the appropriate YAML file for the category"""
    data_file = f"{category}/data.yaml"
    
    if not os.path.exists(data_file):
        print(f"Error: {data_file} not found")
        return None
    
    with open(data_file, 'r') as file:
        return yaml.safe_load(file)

def create_label_prompt(item, category, is_pass=True, label_side="front"):
    """Create a detailed prompt for generating alcohol label images"""
    
    # Define mandatory information that must appear in same field of vision (front label)
    same_field_vision = [
        f"Brand name: {item['brand_name']}",
        f"Class/Type designation: {item['product_type']}",
        f"Alcohol content: {item['alcohol_content']}% by volume"
    ]
    
    # Define information that can appear on any label
    # Get location-specific information based on category
    if category == "beer":
        location = item.get('brewery_location', 'Portland, Oregon')
        bottler = item.get('bottler_name', 'Sample Brewing Co.')
    elif category == "wine":
        location = item.get('winery_location', 'Napa Valley, California')
        bottler = item.get('bottler_name', 'Sample Winery')
    else:  # liquor
        location = item.get('distillery_location', 'Louisville, Kentucky')
        bottler = item.get('bottler_name', 'Sample Distillery')
    
    # Capture exact bottler name as provided (if present) to include verbatim on labels
    exact_bottler_name = item.get('bottler_name')
    
    any_label_info = [
        f"Net contents: {item['net_contents']}",
        f"Name and address: {bottler}, {location}",
        f"Health warning statement: {item.get('health_warning', 'GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.')}"
    ]
    # Ensure the product class/type is explicitly present and exact on back labels as well
    any_label_info.insert(0, f"Class/Type designation (must match exactly, no changes): {item['product_type']}")
    
    # Ensure exact bottler name appears verbatim on labels
    if exact_bottler_name:
        any_label_info.insert(0, f"Include this exact bottler name (verbatim, no changes): {exact_bottler_name}")
    
    # Add category-specific information
    if category == "liquor":
        if 'distillery_location' in item and item['distillery_location']:
            any_label_info.append(f"Distillery location: {item['distillery_location']}")
    elif category == "wine":
        any_label_info.append("Vintage year: 2025")
        if 'winery_location' in item and item['winery_location']:
            any_label_info.append(f"Winery location: {item['winery_location']}")
    elif category == "beer":
        if 'brewery_location' in item and item['brewery_location']:
            any_label_info.append(f"Brewery location: {item['brewery_location']}")
    
    if label_side == "front":
        label_content = same_field_vision + [
            f"Net contents: {item['net_contents']}",
            f"Description: {item['description']}"
        ]
        # Also require the exact bottler name on front labels
        if exact_bottler_name:
            label_content.append(f"Include this exact bottler name (verbatim, no changes): {exact_bottler_name}")
        label_type = "FRONT LABEL"
        layout_notes = "Focus on brand name, product type, and alcohol content prominently displayed together. Include product description and basic information."
    else:
        label_content = any_label_info
        label_type = "BACK LABEL"
        layout_notes = (
            "Include all regulatory information, health warnings, net contents, and detailed product information. "
            "Use smaller, readable text for compliance information. "
            f"Do not invent or alter the product class/type; it must be exactly '{item['product_type']}'."
        )
    
    base_prompt = f"""Create a flat, rectangular alcohol {label_type} design for {item['brand_name']} {item['product_type']}.

    IMPORTANT: Generate ONLY the label itself - NO bottle, NO container, NO 3D effects. Just a flat, rectangular label design.

    This is a {label_type} that should include:
    {chr(10).join(f"- {info}" for info in label_content)}

    Design requirements:
    - Flat, rectangular label design (no bottle or container)
    - Pure white background (#FFFFFF). Do not use transparency.
    - Modern, clean typography appropriate for {label_type}
    - Professional layout with clear hierarchy
    - Appropriate colors for {category}
    - Text should be clearly readable
    - Label proportions should be realistic (like a typical bottle label)
    - Tightly crop the label to its content. Minimize white margins/padding.
    - No large borders; leave at most a very small safety margin (≤10px).
    - {layout_notes}
    """

    # Implement non-compliant variations WITHOUT printing the failure reason on the label
    if not is_pass:
        fail_reason = (item.get('failure_reason') or '').lower()

        # 1) Missing alcohol content statement
        if 'missing alcohol content' in fail_reason and label_side == 'front':
            base_prompt += "\nDo not include any alcohol content statement on this label."

        # 2) Alcohol content format incorrect
        if 'format' in fail_reason and 'alcohol content' in fail_reason:
            base_prompt += "\nShow the alcohol content in an incorrect format (for example: '5.2 ABV' without percent sign, or ambiguous phrasing)."

        # 3) Alcohol content not clearly visible / obscured
        if 'alcohol content not clearly visible' in fail_reason or 'obscured' in fail_reason:
            base_prompt += "\nRender the alcohol content with very low contrast or very small text so it is hard to read."

        # 4) Missing net contents
        if 'missing net contents' in fail_reason and label_side == 'back':
            base_prompt += "\nDo not include any net contents statement on this label."

        # 5) Net contents declaration incorrect (mismatch)
        if 'net contents declaration incorrect' in fail_reason:
            base_prompt += f"\nDisplay a net contents value that does NOT match the expected '{item['net_contents']}' (e.g., show '10 fl oz' if expected is '12 fl oz'). Do NOT add any annotations about the mismatch."

        # 6) Missing brand name
        if 'missing brand name' in fail_reason and label_side == 'front':
            base_prompt += "\nDo not include any brand name text on this label."

        # 7) Text size below minimum requirements
        if 'text size below minimum' in fail_reason:
            base_prompt += "\nUse text that is noticeably too small for key compliance statements (e.g., health warning, alcohol content)."

        # 8) Missing government warning
        if 'missing government warning' in fail_reason and label_side == 'back':
            base_prompt += "\nDo not include any government health warning statement on this label."

        # 9) Label not in English requirement
        if 'not in english' in fail_reason or 'english language requirement' in fail_reason:
            base_prompt += "\nWrite all label copy (except proper nouns like brand names) in French."

        # 10) Country of origin missing (liquor)
        if 'country of origin' in fail_reason and label_side == 'back':
            base_prompt += "\nDo not include a country of origin statement on this label."

        # 11) Age statement missing (liquor)
        if 'age statement' in fail_reason and label_side == 'back':
            base_prompt += "\nDo not include any age statement on this label."

        # Do not include failure reasons or citations on the visual label
        base_prompt += "\nDo not add any annotations or explanations about violations on the label artwork."

    else:
        base_prompt += f"\n\nThis is a COMPLIANT {label_type} that follows all regulatory requirements for {category}."

    return base_prompt

def generate_image(prompt, output_path, overwrite=False):
    """Generate an image using Gemini and save it"""
    # Check if file exists and handle accordingly
    if os.path.exists(output_path) and not overwrite:
        print(f"Skipping existing file: {output_path}")
        return True
    
    try:
        client = get_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[prompt],
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data))
                # Trim surrounding white space to minimize padding
                image = trim_whitespace(image)
                image.save(output_path)
                print(f"Generated: {output_path}")
                return True
            elif part.text is not None:
                print(f"Text response: {part.text}")
        
        return False
    except Exception as e:
        print(f"Error generating image: {e}")
        return False

def generate_category_images(category, overwrite=False, only_id: str | None = None):
    """Generate all images for a specific category"""
    print(f"Generating images for {category}...")
    
    data = load_data_yaml(category)
    if not data:
        return
    
    # Create directories if they don't exist
    pass_front_dir = Path(f"{category}/pass/front")
    pass_back_dir = Path(f"{category}/pass/back")
    fail_front_dir = Path(f"{category}/fail/front")
    fail_back_dir = Path(f"{category}/fail/back")
    
    for dir_path in [pass_front_dir, pass_back_dir, fail_front_dir, fail_back_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Generate pass images (front and back)
    for i, item in enumerate(data['pass'], 1):
        if only_id and item.get('id') != only_id:
            continue
        # Front label
        prompt = create_label_prompt(item, category, is_pass=True, label_side="front")
        if 'id' in item:
            filename = f"{item['id']}_front.png"
        else:
            filename = f"{item['brand_name'].replace(' ', '_').lower()}_pass_{i:02d}_front.png"
        output_path = pass_front_dir / filename
        generate_image(prompt, output_path, overwrite)
        
        # Back label
        prompt = create_label_prompt(item, category, is_pass=True, label_side="back")
        if 'id' in item:
            filename = f"{item['id']}_back.png"
        else:
            filename = f"{item['brand_name'].replace(' ', '_').lower()}_pass_{i:02d}_back.png"
        output_path = pass_back_dir / filename
        generate_image(prompt, output_path, overwrite)
    
    # Generate fail images (front and back)
    for i, item in enumerate(data['fail'], 1):
        if only_id and item.get('id') != only_id:
            continue
        # Front label
        prompt = create_label_prompt(item, category, is_pass=False, label_side="front")
        if 'id' in item:
            filename = f"{item['id']}_front.png"
        else:
            filename = f"{item['brand_name'].replace(' ', '_').lower()}_fail_{i:02d}_front.png"
        output_path = fail_front_dir / filename
        generate_image(prompt, output_path, overwrite)

def trim_whitespace(image: Image.Image, background_color=(255, 255, 255), tolerance: int = 8, safety_margin: int = 6) -> Image.Image:
    """Trim near-white borders from an image while preserving a small safety margin.

    Parameters:
        image: PIL Image to trim.
        background_color: Expected background color tuple.
        tolerance: Allowed per-channel deviation from the background color to still count as background.
        safety_margin: Pixels to keep around detected content after trimming.

    Returns:
        Cropped PIL Image with minimal white padding. Returns original on failure.
    """
    try:
        if image.mode != 'RGB':
            image = image.convert('RGB')

        bg = Image.new('RGB', image.size, background_color)
        # Highlight differences from background; bias by tolerance to ignore near-white
        diff = ImageChops.difference(image, bg)
        diff = ImageChops.add(diff, diff, 2.0, -tolerance)
        bbox = diff.getbbox()
        if not bbox:
            return image

        left, top, right, bottom = bbox
        left = max(left - safety_margin, 0)
        top = max(top - safety_margin, 0)
        right = min(right + safety_margin, image.width)
        bottom = min(bottom + safety_margin, image.height)
        return image.crop((left, top, right, bottom))
    except Exception:
        return image
        
        # Back label
        prompt = create_label_prompt(item, category, is_pass=False, label_side="back")
        if 'id' in item:
            filename = f"{item['id']}_back.png"
        else:
            filename = f"{item['brand_name'].replace(' ', '_').lower()}_fail_{i:02d}_back.png"
        output_path = fail_back_dir / filename
        generate_image(prompt, output_path, overwrite)

def main():
    parser = argparse.ArgumentParser(description='Generate alcohol label images for testing')
    parser.add_argument('--all', action='store_true', help='Generate images for all categories')
    parser.add_argument('--beer', action='store_true', help='Generate images for beer')
    parser.add_argument('--wine', action='store_true', help='Generate images for wine')
    parser.add_argument('--liquor', action='store_true', help='Generate images for liquor')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing images')
    parser.add_argument('--only_id', type=str, default=None, help='Only generate a single item by ID (e.g., beer_pass_004)')
    
    args = parser.parse_args()
    
    if not any([args.all, args.beer, args.wine, args.liquor]):
        print("Please specify at least one category: --all, --beer, --wine, or --liquor")
        return
    
    categories = []
    if args.all or args.beer:
        categories.append('beer')
    if args.all or args.wine:
        categories.append('wine')
    if args.all or args.liquor:
        categories.append('liquor')
    
    for category in categories:
        generate_category_images(category, args.overwrite, args.only_id)
    
    print("Image generation complete!")

if __name__ == "__main__":
    main()