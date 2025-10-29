import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Google Cloud Configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
    GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
    
    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/alcohol_label_verification')
    
    # Application Configuration
    DEFAULT_ROLE = os.getenv('DEFAULT_ROLE', 'admin')
    
    # Streamlit Configuration
    STREAMLIT_SERVER_PORT = int(os.getenv('STREAMLIT_SERVER_PORT', '8501'))
    STREAMLIT_SERVER_ADDRESS = os.getenv('STREAMLIT_SERVER_ADDRESS', '0.0.0.0')
    
    @classmethod
    def validate_config(cls):
        """Validate that required configuration is present"""
        required_vars = [
            'GEMINI_API_KEY',
            'GCP_PROJECT_ID', 
            'GCS_BUCKET_NAME',
            'DATABASE_URL'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True

