import io
import uuid
from datetime import datetime
from google.cloud import storage
from google.cloud.exceptions import NotFound
from config import Config
import streamlit as st

class GCSService:
    def __init__(self):
        """Initialize Google Cloud Storage client"""
        try:
            self.client = storage.Client(project=Config.GCP_PROJECT_ID)
            self.bucket_name = Config.GCS_BUCKET_NAME
            self.bucket = self.client.bucket(self.bucket_name)
        except Exception as e:
            st.error(f"Failed to initialize GCS client: {e}")
            raise
    
    def upload_image(self, file_data, filename=None, content_type='image/jpeg'):
        """
        Upload image file to Google Cloud Storage
        
        Args:
            file_data: File data (bytes or file-like object)
            filename: Optional filename, will generate UUID if not provided
            content_type: MIME type of the file
            
        Returns:
            str: GCS URL of the uploaded file
        """
        try:
            # Generate unique filename if not provided
            if not filename:
                file_extension = self._get_file_extension(content_type)
                filename = f"labels/{uuid.uuid4()}{file_extension}"
            
            # Create blob
            blob = self.bucket.blob(filename)
            
            # Set metadata
            blob.metadata = {
                'uploaded_at': datetime.utcnow().isoformat(),
                'content_type': content_type
            }
            
            # Upload file
            if hasattr(file_data, 'read'):
                # File-like object
                file_data.seek(0)  # Reset file pointer
                blob.upload_from_file(file_data, content_type=content_type)
            else:
                # Bytes data
                blob.upload_from_string(file_data, content_type=content_type)
            
            # Make blob publicly readable (optional, depending on security requirements)
            # blob.make_public()
            
            return f"gs://{self.bucket_name}/{filename}"
            
        except Exception as e:
            st.error(f"Failed to upload image to GCS: {e}")
            raise
    
    def get_image_bytes(self, gcs_url):
        """
        Download image from GCS and return as bytes
        
        Args:
            gcs_url: GCS URL (gs://bucket/path)
            
        Returns:
            bytes: Image data
        """
        try:
            # Extract blob name from GCS URL
            if gcs_url.startswith('gs://'):
                blob_name = gcs_url[5:].split('/', 1)[1]  # Remove 'gs://bucket/' prefix
            else:
                blob_name = gcs_url
            
            blob = self.bucket.blob(blob_name)
            
            if not blob.exists():
                raise NotFound(f"Image not found: {gcs_url}")
            
            return blob.download_as_bytes()
            
        except Exception as e:
            st.error(f"Failed to download image from GCS: {e}")
            raise
    
    def get_public_url(self, gcs_url):
        """
        Get public URL for GCS object (if bucket is public)
        
        Args:
            gcs_url: GCS URL (gs://bucket/path)
            
        Returns:
            str: Public HTTPS URL
        """
        try:
            if gcs_url.startswith('gs://'):
                blob_name = gcs_url[5:].split('/', 1)[1]
            else:
                blob_name = gcs_url
            
            blob = self.bucket.blob(blob_name)
            return blob.public_url
            
        except Exception as e:
            st.error(f"Failed to get public URL: {e}")
            return gcs_url  # Return original URL as fallback
    
    def delete_image(self, gcs_url):
        """
        Delete image from GCS
        
        Args:
            gcs_url: GCS URL (gs://bucket/path)
        """
        try:
            if gcs_url.startswith('gs://'):
                blob_name = gcs_url[5:].split('/', 1)[1]
            else:
                blob_name = gcs_url
            
            blob = self.bucket.blob(blob_name)
            blob.delete()
            
        except Exception as e:
            st.error(f"Failed to delete image from GCS: {e}")
            raise
    
    def _get_file_extension(self, content_type):
        """Get file extension from MIME type"""
        extensions = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp',
            'image/heic': '.heic',
            'image/heif': '.heif'
        }
        return extensions.get(content_type, '.jpg')
    
    def test_connection(self):
        """Test GCS connection and bucket access"""
        try:
            # Try to list objects in bucket (limit to 1 for efficiency)
            list(self.bucket.list_blobs(max_results=1))
            return True
        except Exception as e:
            st.error(f"GCS connection test failed: {e}")
            return False

# Global GCS service instance
gcs_service = GCSService()

