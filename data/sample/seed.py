import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
import yaml

# Ensure we can import from project root (two levels up)
CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Load env explicitly from project root
load_dotenv(PROJECT_ROOT / '.env')

from config import Config  # noqa: E402

# Bootstrap Django so we can use the app's ORM/models
import django  # noqa: E402
backend_path = str(PROJECT_ROOT / 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from backend.core.services import upload_file_to_gcs  # noqa: E402
from django.core.files import File  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from backend.core.models import Company, Location, Submission, SubmissionImage  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description='Seed database with sample YAML data and upload images to GCS')
    parser.add_argument('--all', action='store_true', help='Seed all categories')
    parser.add_argument('--beer', action='store_true', help='Seed beer data')
    parser.add_argument('--wine', action='store_true', help='Seed wine data')
    parser.add_argument('--liquor', action='store_true', help='Seed liquor data')
    parser.add_argument('--only-id', type=str, default=None, help='Only seed a single item by ID (e.g., beer_pass_004)')
    return parser.parse_args()


def load_yaml_for_category(category: str) -> Dict:
    data_file = CURRENT_FILE.parent / category / 'data.yaml'
    if not data_file.exists():
        raise FileNotFoundError(f"Missing data file: {data_file}")
    with open(data_file, 'r') as f:
        return yaml.safe_load(f)


def infer_company_type(category: str) -> str:
    if category == 'beer':
        return 'brewery'
    if category == 'wine':
        return 'winery'
    return 'distillery'


def extract_location_fields(category: str, item: Dict) -> Tuple[str, str, str]:
    # Get the freeform location string
    if category == 'beer':
        raw = item.get('brewery_location', '')
    elif category == 'wine':
        raw = item.get('winery_location', '')
    else:
        raw = item.get('distillery_location', '')

    city, state, country = '', '', 'USA'
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    if len(parts) == 1:
        # Only a city or region provided; store as city
        city = parts[0]
    elif len(parts) >= 2:
        city = parts[0]
        second = parts[1]
        # Heuristic: if second token is a US state name or abbreviation, treat it as state; else as country
        us_states = {
            'alabama','alaska','arizona','arkansas','california','colorado','connecticut','delaware','florida','georgia',
            'hawaii','idaho','illinois','indiana','iowa','kansas','kentucky','louisiana','maine','maryland','massachusetts',
            'michigan','minnesota','mississippi','missouri','montana','nebraska','nevada','new hampshire','new jersey',
            'new mexico','new york','north carolina','north dakota','ohio','oklahoma','oregon','pennsylvania','rhode island',
            'south carolina','south dakota','tennessee','texas','utah','vermont','virginia','washington','west virginia',
            'wisconsin','wyoming'
        }
        token = second.lower()
        if token in us_states or len(token) == 2:  # basic abbrev detection
            state = second
            country = 'USA'
        else:
            state = ''
            country = second
    return city, state, country


def get_company_name(item: Dict) -> str:
    return item.get('bottler_name') or item.get('brewery') or item.get('brand_name')


def ensure_company_and_location(category: str, item: Dict) -> Tuple[Company, Location]:
    company_type = infer_company_type(category)
    company_name = get_company_name(item)
    city, state, country = extract_location_fields(category, item)

    company, _ = Company.objects.get_or_create(name=company_name)

    # Compose a simple location name
    loc_name = f"{city or 'Primary'} {company_type.capitalize()}".strip()
    location, _ = Location.objects.get_or_create(
        company=company,
        name=loc_name,
        defaults={
            'address_line1': '',
            'address_line2': '',
            'city': city or 'Unknown',
            'state': state or '',
            'postal_code': '',
            'country': country or 'USA',
        },
    )

    return company, location


def ensure_demo_user():
    UserModel = get_user_model()
    email = 'demo@example.com'
    user = UserModel.objects.filter(email=email).first()
    if not user:
        # Create a basic staff user without password (for seeding linkage); adjust as needed
        user = UserModel.objects.create(email=email, username='demo', is_staff=True)
    return user


def upload_image_to_gcs(local_path: Path, category: str) -> Optional[str]:
    if not local_path.exists():
        return None
    # Stable, readable path in bucket
    gcs_key = f"labels/{category}/{local_path.name}"
    gs_uri, _ = upload_file_to_gcs(str(local_path), gcs_key)
    return gs_uri


def seed_category(category: str, only_id: Optional[str] = None):
    print(f"Seeding {category}...")
    data = load_yaml_for_category(category)

    user = ensure_demo_user()

    # Handle pass items (front/back)
    for item in data.get('pass', []):
        if only_id and item.get('id') != only_id:
            continue
        company, location = ensure_company_and_location(category, item)

        # File names follow ID-based convention when present
        base_id = item.get('id')
        if base_id:
            front_file = CURRENT_FILE.parent / category / 'pass' / 'front' / f"{base_id}_front.png"
            back_file = CURRENT_FILE.parent / category / 'pass' / 'back' / f"{base_id}_back.png"
        else:
            # Fallback: upload all pngs matching brand if needed (not expected here)
            front_file = None
            back_file = None

        # Upload and insert submissions for each existing side
        for side, file_path in [('front', front_file), ('back', back_file)]:
            if not file_path:
                continue
            gcs_url = upload_image_to_gcs(file_path, category)
            if not gcs_url:
                continue
            submission = Submission.objects.create(
                user=user,
                company=company,
                location=location,
                gcs_uri=gcs_url,
                brand_name=item.get('brand_name', ''),
                product_class_type=item.get('product_type', ''),
                alcohol_content=f"{item.get('alcohol_content', '')}%" if item.get('alcohol_content') is not None else '',
                net_contents=item.get('net_contents', ''),
                status=Submission.STATUS_PENDING,
            )
            # Attach image file to SubmissionImage
            try:
                with open(file_path, 'rb') as f:
                    img = SubmissionImage.objects.create(submission=submission, gcs_uri=gcs_url)
                    img.image.save(file_path.name, File(f), save=True)
            except Exception as e:
                print(f"Failed to attach image file {file_path}: {e}")

    # Handle fail items (commonly only front exists)
    for item in data.get('fail', []):
        if only_id and item.get('id') != only_id:
            continue
        company, location = ensure_company_and_location(category, item)

        base_id = item.get('id')
        candidates = []
        if base_id:
            # Prefer front, also try back if present in data folder
            candidates.append(CURRENT_FILE.parent / category / 'fail' / 'front' / f"{base_id}_front.png")
            candidates.append(CURRENT_FILE.parent / category / 'fail' / 'back' / f"{base_id}_back.png")

        for file_path in candidates:
            gcs_url = upload_image_to_gcs(file_path, category)
            if not gcs_url:
                continue
            submission = Submission.objects.create(
                user=ensure_demo_user(),
                company=company,
                location=location,
                gcs_uri=gcs_url,
                brand_name=item.get('brand_name', ''),
                product_class_type=item.get('product_type', ''),
                alcohol_content=f"{item.get('alcohol_content', '')}%" if item.get('alcohol_content') is not None else '',
                net_contents=item.get('net_contents', ''),
                status=Submission.STATUS_PENDING,
            )
            try:
                with open(file_path, 'rb') as f:
                    img = SubmissionImage.objects.create(submission=submission, gcs_uri=gcs_url)
                    img.image.save(file_path.name, File(f), save=True)
            except Exception as e:
                print(f"Failed to attach image file {file_path}: {e}")


def main():
    args = parse_args()

    if not any([args.all, args.beer, args.wine, args.liquor]):
        print('Please specify at least one category: --all, --beer, --wine, or --liquor')
        return

    # Validate minimal config for GCS/DB
    missing = []
    if not Config.GCS_BUCKET_NAME:
        missing.append('GCS_BUCKET_NAME')
    if not Config.GCP_PROJECT_ID:
        missing.append('GCP_PROJECT_ID')
    if not Config.DATABASE_URL:
        missing.append('DATABASE_URL')
    if missing:
        raise RuntimeError(f"Missing required env: {', '.join(missing)}")

    categories = []
    if args.all or args.beer:
        categories.append('beer')
    if args.all or args.wine:
        categories.append('wine')
    if args.all or args.liquor:
        categories.append('liquor')

    for category in categories:
        seed_category(category, args.only_id)

    print('Seeding complete!')


if __name__ == '__main__':
    main()


