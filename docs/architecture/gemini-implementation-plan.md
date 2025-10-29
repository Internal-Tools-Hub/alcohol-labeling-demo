# Updated Implementation Plan: Gemini 2.5 Flash + Docker Compose

## Architecture Changes

### Previous vs. New Approach

**Before:**
- Google Cloud Vision API for OCR → Extract text → Fuzzy match with form data
- Manual text parsing and field extraction
- Separate verification logic

**After (Gemini 2.5 Flash):**
- Gemini 2.5 Flash multimodal analysis → Direct structured extraction + verification
- Prompt engineering for label-specific information extraction
- Single API call for both extraction AND comparison
- Leverages Gemini's reasoning capabilities for better accuracy

### Key Advantages of Gemini 2.5 Flash

1. **Multimodal Understanding**: Analyzes image context, not just text
2. **Structured Output**: Can return JSON with extracted fields directly
3. **Built-in Reasoning**: Understands label layouts and conventions
4. **Cost Effective**: Gemini 2.5 Flash pricing is competitive
5. **Context Awareness**: Can identify government warnings, ABV formats, etc.
6. **Comparison Logic**: Can perform verification in same API call

---

## Updated Technical Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Streamlit | Web UI |
| AI/ML | **Gemini 2.5 Flash** | Image analysis & verification |
| Database | PostgreSQL 18 | Metadata storage |
| Storage | Google Cloud Storage | Image storage |
| Orchestration | **Docker Compose** | Container management |
| Web Server | Nginx (in container) | Reverse proxy + SSL |
| Language | Python 3.11+ | Application code |

---

## Docker Compose Architecture

```yaml
# Two deployment modes:
# 1. Standalone: App + PostgreSQL in containers
# 2. External DB: App in container, PostgreSQL on external host
```

### Container Structure

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                          │
│  ┌────────────────┐      ┌─────────────────┐           │
│  │   Nginx        │      │   Streamlit     │           │
│  │   (Reverse     │─────▶│   App           │           │
│  │    Proxy)      │      │   (Python)      │           │
│  └────────────────┘      └─────────┬───────┘           │
│         │                           │                    │
│         │                           │                    │
│         ▼                           ▼                    │
│  ┌────────────────┐      ┌─────────────────┐           │
│  │  Let's Encrypt │      │   PostgreSQL    │           │
│  │  Certbot       │      │   (Optional)    │◀──────────┼─── OR External PostgreSQL
│  └────────────────┘      └─────────────────┘           │
│                                    │                    │
└────────────────────────────────────┼────────────────────┘
                                     │
                                     ▼
                          Google Cloud Storage (GCS)
                          Gemini API (Google AI)
```

---

## Gemini 2.5 Flash Integration

### Service Architecture

```python
# services/gemini_service.py

import google.generativeai as genai
from PIL import Image
import json
from typing import Dict, Any, Optional

class GeminiLabelAnalyzer:
    """
    Uses Gemini 2.5 Flash to analyze alcohol labels.

    Capabilities:
    1. Extract structured label information (brand, ABV, contents, etc.)
    2. Verify extracted info against submitted form data
    3. Identify government warnings and compliance elements
    4. Provide confidence scores and reasoning
    """

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def analyze_and_verify_label(
        self,
        image_bytes: bytes,
        submitted_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Single API call to:
        1. Extract label information
        2. Compare with submitted data
        3. Return structured verification results
        """

        prompt = self._build_verification_prompt(submitted_data)

        # Convert bytes to PIL Image
        image = Image.open(io.BytesIO(image_bytes))

        # Make API call with structured output
        response = self.model.generate_content(
            [prompt, image],
            generation_config={
                "temperature": 0.1,  # Low temperature for consistent extraction
                "response_mime_type": "application/json"
            }
        )

        # Parse structured response
        result = json.loads(response.text)

        return result

    def _build_verification_prompt(self, submitted_data: Dict) -> str:
        """Build prompt for Gemini with submitted form data."""

        return f"""You are an expert alcohol label verification system for the TTB (Alcohol and Tobacco Tax and Trade Bureau).

Analyze this alcohol beverage label image and perform the following tasks:

## SUBMITTED INFORMATION (from application form):
- Brand Name: {submitted_data['brand_name']}
- Product Class/Type: {submitted_data['product_class']}
- Alcohol Content (ABV): {submitted_data['alcohol_content_abv']}%
- Net Contents: {submitted_data['net_contents']}

## YOUR TASKS:

1. **Extract Information from Label Image:**
   - Identify the brand name as it appears on the label
   - Identify the product class/type (e.g., "Bourbon Whiskey", "IPA Beer", etc.)
   - Locate and extract the alcohol content percentage
   - Locate and extract the net contents/volume
   - Check for the presence of the mandatory GOVERNMENT WARNING statement

2. **Verify Each Field:**
   For each field, compare what you see on the label with the submitted information:
   - Use case-insensitive comparison for text fields
   - Allow minor formatting differences (e.g., "45%" vs "45.0% ABV")
   - For alcohol content, allow ±0.5% tolerance
   - For net contents, normalize units (750ml = 750 mL)
   - Consider OCR-like variations (e.g., "O" vs "0")

3. **Government Warning Check:**
   - Verify the presence of "GOVERNMENT WARNING" text
   - Note if the warning statement appears complete

## OUTPUT FORMAT (JSON):

Return your analysis as valid JSON matching this exact structure:

{{
  "extraction": {{
    "brand_name": {{
      "found": true/false,
      "value": "extracted brand name or null",
      "confidence": 0.0-1.0,
      "location": "where found on label (e.g., 'top center')"
    }},
    "product_class": {{
      "found": true/false,
      "value": "extracted product type or null",
      "confidence": 0.0-1.0,
      "location": "where found"
    }},
    "alcohol_content": {{
      "found": true/false,
      "value": numeric value or null,
      "formatted": "as shown on label (e.g., '45% Alc./Vol.')",
      "confidence": 0.0-1.0,
      "location": "where found"
    }},
    "net_contents": {{
      "found": true/false,
      "value": "extracted volume with units or null",
      "confidence": 0.0-1.0,
      "location": "where found"
    }},
    "government_warning": {{
      "found": true/false,
      "complete": true/false,
      "preview": "first 50 chars of warning text or null",
      "confidence": 0.0-1.0
    }}
  }},
  "verification": {{
    "brand_name": {{
      "match": true/false,
      "score": 0.0-1.0,
      "reason": "explanation of match/mismatch",
      "submitted": "{submitted_data['brand_name']}",
      "extracted": "value from extraction"
    }},
    "product_class": {{
      "match": true/false,
      "score": 0.0-1.0,
      "reason": "explanation",
      "submitted": "{submitted_data['product_class']}",
      "extracted": "value from extraction"
    }},
    "alcohol_content": {{
      "match": true/false,
      "score": 0.0-1.0,
      "reason": "explanation",
      "submitted": {submitted_data['alcohol_content_abv']},
      "extracted": numeric value or null
    }},
    "net_contents": {{
      "match": true/false,
      "score": 0.0-1.0,
      "reason": "explanation",
      "submitted": "{submitted_data['net_contents']}",
      "extracted": "value from extraction"
    }},
    "government_warning": {{
      "match": true/false,
      "score": 0.0-1.0,
      "reason": "explanation"
    }}
  }},
  "overall": {{
    "status": "all_match" | "partial_match" | "no_match" | "error",
    "match_count": number of matching fields,
    "total_fields": 5,
    "confidence": average confidence score 0.0-1.0,
    "recommendation": "APPROVE" | "REJECT" | "MANUAL_REVIEW",
    "summary": "brief explanation of overall assessment"
  }},
  "image_quality": {{
    "readable": true/false,
    "clarity": 0.0-1.0,
    "issues": ["list of any quality issues detected"]
  }}
}}

## IMPORTANT RULES:
- Be strict but fair in comparisons
- Explain your reasoning clearly
- If text is unclear, note it in confidence scores
- Consider common alcohol label formats and conventions
- Return only valid JSON, no additional commentary
"""
```

---

## Docker Compose Configuration

### File: `docker-compose.yml`

```yaml
version: '3.8'

services:
  # PostgreSQL Database (Optional - can use external)
  postgres:
    image: postgres:18-alpine
    container_name: alcohol-labels-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-alcohol_app}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-alcohol_labels}
      POSTGRES_INITDB_ARGS: "-E UTF8"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-alcohol_app}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app-network
    # Conditional: only start if not using external DB
    profiles:
      - local-db

  # Streamlit Application
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: alcohol-labels-app
    restart: unless-stopped
    environment:
      # Application
      ENV: ${ENV:-production}
      DEBUG: ${DEBUG:-false}

      # Database connection - supports both local and external
      DB_HOST: ${DB_HOST:-postgres}
      DB_PORT: ${DB_PORT:-5432}
      DB_NAME: ${DB_NAME:-alcohol_labels}
      DB_USER: ${DB_USER:-alcohol_app}
      DB_PASSWORD: ${DB_PASSWORD}

      # Google Cloud
      GCS_PROJECT_ID: ${GCS_PROJECT_ID}
      GCS_BUCKET_NAME: ${GCS_BUCKET_NAME}
      GOOGLE_APPLICATION_CREDENTIALS: /app/credentials/gcp-key.json

      # Gemini API
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GEMINI_MODEL: ${GEMINI_MODEL:-gemini-2.5-flash}

      # Streamlit
      STREAMLIT_SERVER_PORT: 8501
      STREAMLIT_SERVER_ADDRESS: 0.0.0.0
      STREAMLIT_SERVER_HEADLESS: true
      STREAMLIT_BROWSER_GATHER_USAGE_STATS: false

    volumes:
      # Mount GCP credentials (read-only)
      - ${GCP_CREDENTIALS_PATH}:/app/credentials/gcp-key.json:ro
      # Mount config for easy updates
      - ./.streamlit:/app/.streamlit:ro
    ports:
      - "${APP_PORT:-8501}:8501"
    depends_on:
      postgres:
        condition: service_healthy
        required: false  # Only if using local-db profile
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - app-network

  # Nginx Reverse Proxy with SSL
  nginx:
    image: nginx:alpine
    container_name: alcohol-labels-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
    depends_on:
      - app
    networks:
      - app-network
    command: "/bin/sh -c 'while :; do sleep 6h & wait $${!}; nginx -s reload; done & nginx -g \"daemon off;\"'"

  # Certbot for SSL certificates
  certbot:
    image: certbot/certbot
    container_name: alcohol-labels-certbot
    restart: unless-stopped
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"

volumes:
  postgres_data:
    driver: local

networks:
  app-network:
    driver: bridge
```

### File: `docker-compose.override.yml` (for local development)

```yaml
version: '3.8'

services:
  app:
    build:
      target: development
    environment:
      ENV: development
      DEBUG: true
      STREAMLIT_SERVER_RUN_ON_SAVE: true
    volumes:
      # Mount source code for live reload
      - .:/app
      - /app/__pycache__
      - /app/.pytest_cache
    ports:
      - "8501:8501"
      - "5678:5678"  # debugpy port
    command: streamlit run Home.py --server.runOnSave true

  postgres:
    ports:
      - "5432:5432"  # Expose for local DB tools
```

---

## Dockerfile (Multi-stage)

### File: `Dockerfile`

```dockerfile
# Multi-stage build for optimized production image

# Stage 1: Base image with dependencies
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Development image (with dev tools)
FROM base as development

RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    black \
    flake8 \
    debugpy

COPY . .

EXPOSE 8501 5678

CMD ["python", "-m", "debugpy", "--listen", "0.0.0.0:5678", "-m", "streamlit", "run", "Home.py"]

# Stage 3: Production image (optimized)
FROM base as production

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser . .

# Create directories for credentials and config
RUN mkdir -p /app/credentials /app/.streamlit && \
    chown -R appuser:appuser /app/credentials /app/.streamlit

# Switch to non-root user
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "Home.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

## Environment Configuration

### File: `.env.example`

```bash
# =============================================================================
# Alcohol Label Verification - Environment Configuration
# =============================================================================

# -----------------------------------------------------------------------------
# Deployment Mode
# -----------------------------------------------------------------------------
ENV=production  # production | development
DEBUG=false

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------
# OPTION 1: Use local PostgreSQL in Docker (default)
# Set DB_HOST=postgres and enable local-db profile
DB_HOST=postgres
POSTGRES_USER=alcohol_app
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=alcohol_labels
DB_PORT=5432

# OPTION 2: Use external PostgreSQL (hosted on VM or managed service)
# Uncomment and configure these, then disable local-db profile
# DB_HOST=192.168.1.100  # External PostgreSQL IP
# POSTGRES_USER=alcohol_app
# POSTGRES_PASSWORD=external_db_password
# POSTGRES_DB=alcohol_labels
# DB_PORT=5432

# Database connection pooling
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# -----------------------------------------------------------------------------
# Google Cloud Configuration
# -----------------------------------------------------------------------------
GCS_PROJECT_ID=your-gcp-project-id
GCS_BUCKET_NAME=alcohol-label-images
GCP_CREDENTIALS_PATH=./credentials/gcp-service-account.json
GCS_SIGNED_URL_EXPIRATION_HOURS=24

# -----------------------------------------------------------------------------
# Gemini API Configuration
# -----------------------------------------------------------------------------
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS=30
GEMINI_MAX_RETRIES=3

# -----------------------------------------------------------------------------
# Application Settings
# -----------------------------------------------------------------------------
APP_NAME="Alcohol Label Verification"
APP_VERSION=1.0.0
APP_PORT=8501
MAX_UPLOAD_SIZE_MB=10

# -----------------------------------------------------------------------------
# SSL/Domain Configuration
# -----------------------------------------------------------------------------
DOMAIN=yourdomain.com
CERTBOT_EMAIL=admin@yourdomain.com

# -----------------------------------------------------------------------------
# Demo Mode (disable for production)
# -----------------------------------------------------------------------------
DEMO_MODE=true
DEMO_USER_EMAIL=demo@example.com
```

### File: `.env.local` (for local development)

```bash
ENV=development
DEBUG=true
DB_HOST=localhost  # Connect directly to local PostgreSQL
DEMO_MODE=true
```

---

## Deployment Options

### Option 1: Standalone (PostgreSQL in Docker)

```bash
# Use docker-compose with local database profile
docker-compose --profile local-db up -d

# Services started:
# - postgres (containerized)
# - app
# - nginx
# - certbot
```

**Use when:**
- Simple deployment
- Single VM setup
- Development/testing
- Low to medium traffic

### Option 2: External Database

```bash
# Configure .env with external DB settings
DB_HOST=192.168.1.100  # Your external PostgreSQL server

# Start without local-db profile
docker-compose up -d

# Services started:
# - app (connects to external DB)
# - nginx
# - certbot
```

**Use when:**
- Managed PostgreSQL (AWS RDS, Google Cloud SQL, etc.)
- Database on separate VM
- Shared database across services
- High availability requirements
- Automatic backups needed

---

## Updated Service Implementation

### File: `services/gemini_service.py`

```python
import google.generativeai as genai
from google.api_core import retry, exceptions
from PIL import Image
import io
import json
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from config.settings import settings
from utils.error_handler import AppError, handle_errors

logger = logging.getLogger(__name__)

class GeminiAnalysisError(AppError):
    """Gemini API specific errors."""
    pass

class GeminiLabelAnalyzer:
    """
    Gemini 2.5 Flash-powered alcohol label analysis service.

    Replaces traditional OCR + text matching with AI-native approach:
    - Single API call for extraction + verification
    - Contextual understanding of label layouts
    - Built-in reasoning for comparison logic
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        """
        Initialize Gemini service.

        Args:
            api_key: Gemini API key (defaults to settings)
            model_name: Model to use (defaults to settings)
        """
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL

        if not self.api_key:
            raise GeminiAnalysisError(
                "GEMINI_API_KEY not configured",
                user_message="AI service not properly configured"
            )

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

        logger.info(f"Initialized Gemini service with model: {self.model_name}")

    @handle_errors
    def analyze_and_verify_label(
        self,
        image_bytes: bytes,
        submitted_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze label image and verify against submitted form data.

        This is the main service method that replaces separate OCR + comparison steps.

        Args:
            image_bytes: Raw image file bytes
            submitted_data: Form data dict with keys:
                - brand_name (str)
                - product_class (str)
                - alcohol_content_abv (float)
                - net_contents (str)

        Returns:
            Dict with structure:
            {
                "extraction": {...},      # What was found on label
                "verification": {...},    # Field-by-field comparison
                "overall": {...},         # Summary and recommendation
                "image_quality": {...},   # Image readability assessment
                "metadata": {...}         # Processing metadata
            }

        Raises:
            GeminiAnalysisError: If API call fails
        """
        start_time = datetime.now()

        try:
            # Prepare image
            image = Image.open(io.BytesIO(image_bytes))

            # Build prompt with submitted data
            prompt = self._build_verification_prompt(submitted_data)

            # Call Gemini API with retry logic
            response = self._call_gemini_api(prompt, image)

            # Parse JSON response
            result = self._parse_response(response)

            # Add metadata
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result["metadata"] = {
                "model": self.model_name,
                "processing_time_ms": processing_time,
                "api_version": "gemini-2.5-flash",
                "timestamp": datetime.now().isoformat()
            }

            logger.info(
                f"Label analysis completed in {processing_time:.2f}ms. "
                f"Status: {result['overall']['status']}"
            )

            return result

        except exceptions.GoogleAPIError as e:
            logger.error(f"Gemini API error: {e}")
            raise GeminiAnalysisError(
                str(e),
                user_message="AI analysis service temporarily unavailable"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            raise GeminiAnalysisError(
                "Invalid API response format",
                user_message="Analysis failed due to unexpected response"
            )

    @retry.Retry(
        predicate=retry.if_transient_error,
        initial=1.0,
        maximum=10.0,
        multiplier=2.0,
        timeout=settings.GEMINI_TIMEOUT_SECONDS
    )
    def _call_gemini_api(self, prompt: str, image: Image.Image) -> Any:
        """
        Make API call to Gemini with retry logic.

        Args:
            prompt: Verification prompt
            image: PIL Image object

        Returns:
            Gemini API response
        """
        response = self.model.generate_content(
            [prompt, image],
            generation_config=genai.GenerationConfig(
                temperature=0.1,  # Low temperature for consistent extraction
                top_p=0.95,
                top_k=40,
                max_output_tokens=2048,
                response_mime_type="application/json"
            ),
            safety_settings={
                genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            }
        )

        return response

    def _build_verification_prompt(self, submitted_data: Dict[str, Any]) -> str:
        """Build detailed verification prompt for Gemini."""

        # [Prompt from earlier in this document - the comprehensive one]
        # ... (full prompt here)

        return prompt  # Return the comprehensive prompt

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse and validate Gemini response.

        Args:
            response: Gemini API response object

        Returns:
            Validated dict with expected structure

        Raises:
            json.JSONDecodeError: If response is not valid JSON
            GeminiAnalysisError: If response structure is invalid
        """
        # Extract text from response
        response_text = response.text

        # Parse JSON
        result = json.loads(response_text)

        # Validate structure (basic checks)
        required_keys = ["extraction", "verification", "overall", "image_quality"]
        for key in required_keys:
            if key not in result:
                raise GeminiAnalysisError(
                    f"Missing required key in response: {key}",
                    user_message="Incomplete analysis result"
                )

        return result

    def extract_only(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Extract label information without verification (exploration mode).

        Useful for:
        - Pre-filling form fields
        - Understanding what's on the label
        - Debugging/testing

        Args:
            image_bytes: Raw image file bytes

        Returns:
            Dict with extraction results only
        """
        prompt = """Analyze this alcohol beverage label image and extract all visible information.

Return a JSON object with this structure:
{
  "brand_name": "extracted brand or null",
  "product_class": "type of alcohol or null",
  "alcohol_content": numeric ABV or null,
  "net_contents": "volume with units or null",
  "government_warning": true/false,
  "additional_info": {
    "producer": "bottler/producer name or null",
    "origin": "country/region or null",
    "vintage": "year or null",
    "other_text": ["any other notable text"]
  }
}"""

        image = Image.open(io.BytesIO(image_bytes))
        response = self._call_gemini_api(prompt, image)
        return json.loads(response.text)
```

---

## Updated Requirements

### File: `requirements.txt`

```txt
# Core Framework
streamlit==1.31.0
python-dotenv==1.0.0

# Database
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
alembic==1.13.1

# Google Cloud & Gemini
google-cloud-storage==2.14.0
google-generativeai==0.8.0  # Gemini API SDK
google-api-core==2.15.0     # For retry logic

# Image Processing
Pillow==10.2.0

# Configuration & Validation
pydantic==2.6.0
pydantic-settings==2.1.0

# Utilities
requests==2.31.0
tenacity==8.2.3  # Additional retry utilities

# Development
pytest==8.0.0
pytest-cov==4.1.0
pytest-docker==2.0.0  # For testing with Docker
black==24.1.0
flake8==7.0.0
```

---

## Configuration Updates

### File: `config/settings.py` (Updated)

```python
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    # ... (existing settings)

    # Gemini Configuration
    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", env="GEMINI_MODEL")
    GEMINI_TIMEOUT_SECONDS: int = Field(default=30, env="GEMINI_TIMEOUT_SECONDS")
    GEMINI_MAX_RETRIES: int = Field(default=3, env="GEMINI_MAX_RETRIES")

    # Database - flexible for Docker or external
    DB_HOST: str = Field(..., env="DB_HOST")  # Can be 'postgres' (Docker) or IP
    DB_PORT: int = Field(default=5432, env="DB_PORT")
    DB_NAME: str = Field(..., env="DB_NAME")
    DB_USER: str = Field(..., env="DB_USER")
    DB_PASSWORD: str = Field(..., env="DB_PASSWORD")

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def is_docker_db(self) -> bool:
        """Check if using Docker Compose PostgreSQL."""
        return self.DB_HOST == "postgres"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

---

## Deployment Commands

### Local Development

```bash
# Start with local PostgreSQL
docker-compose --profile local-db -f docker-compose.yml -f docker-compose.override.yml up

# Start with external PostgreSQL
DB_HOST=192.168.1.100 docker-compose up
```

### Production Deployment

```bash
# 1. Clone repository on VM
git clone <repo-url>
cd alcohol-labeling-demo

# 2. Copy and configure environment
cp .env.example .env
nano .env  # Configure all settings

# 3. Copy GCP credentials
mkdir -p credentials
scp gcp-service-account.json user@vm:/path/to/app/credentials/

# 4a. Deploy with local PostgreSQL
docker-compose --profile local-db up -d

# 4b. Deploy with external PostgreSQL
docker-compose up -d

# 5. Initialize SSL certificates
docker-compose run --rm certbot certonly --webroot \
  --webroot-path=/var/www/certbot \
  --email ${CERTBOT_EMAIL} \
  --agree-tos \
  --no-eff-email \
  -d ${DOMAIN}

# 6. Restart nginx to load certificates
docker-compose restart nginx

# 7. Check status
docker-compose ps
docker-compose logs -f app
```

### Database Migration (if using external PostgreSQL)

```bash
# Connect to external PostgreSQL
psql -h <external-db-host> -U alcohol_app -d alcohol_labels

# Run init script
\i migrations/init.sql
```

---

## Key Benefits of This Architecture

### Gemini 2.5 Flash Advantages

1. **Unified Processing**: Single API call vs. OCR → parsing → comparison pipeline
2. **Contextual Understanding**: Knows what a bourbon label looks like vs. beer label
3. **Flexible Extraction**: Can handle varied label layouts without rigid templates
4. **Built-in Reasoning**: Explains why fields match/don't match
5. **Cost Efficient**: Competitive pricing, high rate limits
6. **JSON Output**: Structured responses reduce parsing errors

### Docker Compose Advantages

1. **Reproducible Deployments**: Same environment dev → staging → production
2. **Easy Rollbacks**: Tag images, roll back to previous versions
3. **Resource Management**: CPU/memory limits per container
4. **Scalability**: Can scale app containers independently
5. **Isolated Services**: Database issues don't crash app and vice versa
6. **Flexible Database**: Switch between local/external DB with .env change

---

## Next Steps

1. **Review Gemini docs** you mentioned (please share)
2. **Create Docker files** (Dockerfile, docker-compose.yml)
3. **Implement GeminiLabelAnalyzer** service
4. **Update Streamlit UI** to use Gemini service
5. **Test locally** with Docker Compose
6. **Deploy to VM** with chosen database option

Would you like me to start implementing any of these components?
