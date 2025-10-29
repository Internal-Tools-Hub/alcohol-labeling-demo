import streamlit as st
import io
import base64
from datetime import datetime
from PIL import Image
import pandas as pd

# Import our services and models
from config import Config
from src.models.database import db_manager, User, Submission, VerificationResult
from src.services.gcs_service import gcs_service
from src.services.gemini_service import gemini_service
from src.services.verification_service import verification_service

# Page configuration
st.set_page_config(
    page_title="Alcohol Label Verification",
    page_icon="🍷",
    layout="wide",
    initial_sidebar_state="expanded"
)

def init_session_state():
    """Initialize session state variables"""
    if 'user_role' not in st.session_state:
        st.session_state.user_role = Config.DEFAULT_ROLE
    if 'current_user_id' not in st.session_state:
        st.session_state.current_user_id = 1  # Demo user ID
    if 'submission_results' not in st.session_state:
        st.session_state.submission_results = None

def get_current_user():
    """Get current user from database"""
    session = db_manager.get_session()
    try:
        user = session.query(User).filter(User.id == st.session_state.current_user_id).first()
        if not user:
            # Create demo user if not exists
            user = User(email='demo@example.com', role='admin')
            session.add(user)
            session.commit()
            st.session_state.current_user_id = user.id
        return user
    finally:
        session.close()

def render_header():
    """Render application header with role toggle"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.title("🍷 Alcohol Label Verification App")
        st.markdown("**TTB Label Verification System** - Verify alcohol labels against submitted data")
    
    with col2:
        user = get_current_user()
        if user.role == 'admin':
            st.markdown("**Current Role:** Admin")
            if st.button("Switch to Submitter"):
                st.session_state.user_role = 'submitter'
                st.rerun()
        else:
            st.markdown("**Current Role:** Submitter")
            if st.button("Switch to Admin"):
                st.session_state.user_role = 'admin'
                st.rerun()

def render_sidebar():
    """Render sidebar with navigation"""
    st.sidebar.title("Navigation")
    
    user = get_current_user()
    
    if user.role == 'admin':
        if st.sidebar.button("📊 View All Submissions"):
            st.session_state.page = "admin_history"
            st.rerun()
    
    if st.sidebar.button("🏠 Home"):
        st.session_state.page = "home"
        st.rerun()
    
    # Connection status
    st.sidebar.markdown("---")
    st.sidebar.markdown("### System Status")
    
    # Test connections
    try:
        gcs_status = gcs_service.test_connection()
        gemini_status = gemini_service.test_connection()
        
        if gcs_status:
            st.sidebar.success("✅ GCS Connected")
        else:
            st.sidebar.error("❌ GCS Error")
            
        if gemini_status:
            st.sidebar.success("✅ Gemini API Connected")
        else:
            st.sidebar.error("❌ Gemini API Error")
    except Exception as e:
        st.sidebar.error(f"❌ Connection Error: {str(e)}")

def render_submission_form():
    """Render the main submission form"""
    st.header("Submit Label for Verification")
    
    with st.form("label_verification_form"):
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Product Information")
            
            brand_name = st.text_input(
                "Brand Name *",
                placeholder="e.g., Old Tom Distillery",
                help="The brand name as it appears on the label"
            )
            
            product_type = st.text_input(
                "Product Type/Class *",
                placeholder="e.g., Kentucky Straight Bourbon Whiskey",
                help="The type or class designation of the beverage"
            )
            
            alcohol_content = st.number_input(
                "Alcohol Content (%) *",
                min_value=0.0,
                max_value=100.0,
                value=40.0,
                step=0.1,
                help="Alcohol by volume percentage"
            )
            
            net_contents = st.text_input(
                "Net Contents (Optional)",
                placeholder="e.g., 750 mL, 12 fl oz",
                help="Volume of the product"
            )
        
        with col2:
            st.subheader("Label Image")
            
            uploaded_file = st.file_uploader(
                "Upload Label Image *",
                type=['jpg', 'jpeg', 'png', 'webp'],
                help="Upload a clear image of the alcohol label"
            )
            
            if uploaded_file:
                # Display image preview
                image = Image.open(uploaded_file)
                st.image(image, caption="Label Preview", use_column_width=True)
        
        # Submit button
        submitted = st.form_submit_button(
            "🔍 Verify Label",
            type="primary",
            use_container_width=True
        )
        
        if submitted:
            if not all([brand_name, product_type, alcohol_content, uploaded_file]):
                st.error("Please fill in all required fields and upload an image.")
            else:
                process_submission(brand_name, product_type, alcohol_content, net_contents, uploaded_file)

def process_submission(brand_name, product_type, alcohol_content, net_contents, uploaded_file):
    """Process the label verification submission"""
    try:
        # Show processing status
        with st.spinner("Processing label verification..."):
            
            # Prepare form data
            form_data = {
                'brand_name': brand_name,
                'product_type': product_type,
                'alcohol_content': float(alcohol_content),
                'net_contents': net_contents if net_contents else None
            }
            
            # Upload image to GCS
            image_bytes = uploaded_file.read()
            content_type = uploaded_file.type
            
            gcs_url = gcs_service.upload_image(
                image_bytes, 
                content_type=content_type
            )
            
            # Extract text using Gemini
            extracted_data = gemini_service.extract_label_text(
                image_bytes, 
                content_type
            )
            
            # Verify fields
            verification_results = verification_service.compare_fields(
                form_data, 
                extracted_data
            )
            
            # Get overall status
            overall_status, overall_confidence = verification_service.get_overall_status(verification_results)
            
            # Save to database
            submission = save_submission(
                form_data, 
                gcs_url, 
                overall_status, 
                verification_results,
                extracted_data
            )
            
            # Store results in session state
            st.session_state.submission_results = {
                'submission_id': submission.id,
                'form_data': form_data,
                'extracted_data': extracted_data,
                'verification_results': verification_results,
                'overall_status': overall_status,
                'overall_confidence': overall_confidence,
                'image_url': gcs_url
            }
            
            st.success("Label verification completed!")
            st.rerun()
            
    except Exception as e:
        st.error(f"Error processing submission: {str(e)}")
        st.exception(e)

def save_submission(form_data, gcs_url, status, verification_results, extracted_data):
    """Save submission and results to database"""
    session = db_manager.get_session()
    try:
        # Create submission
        submission = Submission(
            user_id=st.session_state.current_user_id,
            brand_name=form_data['brand_name'],
            product_type=form_data['product_type'],
            alcohol_content=form_data['alcohol_content'],
            net_contents=form_data.get('net_contents'),
            image_url=gcs_url,
            status=status
        )
        session.add(submission)
        session.flush()  # Get the ID
        
        # Create verification results
        for field_name, result in verification_results.items():
            verification_result = VerificationResult(
                submission_id=submission.id,
                field_name=field_name,
                expected_value=str(result.get('expected', '')),
                extracted_value=str(result.get('extracted', '')),
                match_status=result.get('matched', False),
                confidence_score=result.get('confidence', 0.0),
                details=result.get('details', '')
            )
            session.add(verification_result)
        
        session.commit()
        return submission
        
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def render_results():
    """Render verification results"""
    if not st.session_state.submission_results:
        return
    
    results = st.session_state.submission_results
    
    st.header("Verification Results")
    
    # Overall status
    status = results['overall_status']
    confidence = results['overall_confidence']
    
    if status == 'matched':
        st.success(f"✅ **Label Matches Form Data** (Confidence: {confidence:.1%})")
    elif status == 'partial':
        st.warning(f"⚠️ **Partial Match** (Confidence: {confidence:.1%})")
    else:
        st.error(f"❌ **Label Does Not Match Form Data** (Confidence: {confidence:.1%})")
    
    # Detailed results table
    st.subheader("Field-by-Field Comparison")
    
    # Prepare data for display
    display_data = []
    for field_name, result in results['verification_results'].items():
        display_data.append({
            'Field': field_name.replace('_', ' ').title(),
            'Expected': result.get('expected', 'N/A'),
            'Extracted': result.get('extracted', 'N/A'),
            'Status': '✅ Match' if result.get('matched') else '❌ Mismatch',
            'Confidence': f"{result.get('confidence', 0):.1%}",
            'Details': result.get('details', '')
        })
    
    df = pd.DataFrame(display_data)
    st.dataframe(df, use_container_width=True)
    
    # Extracted data summary
    st.subheader("Extracted Label Information")
    extracted = results['extracted_data']
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Brand Name", extracted.get('brand_name', 'Not found'))
        st.metric("Product Type", extracted.get('product_type', 'Not found'))
    with col2:
        st.metric("Alcohol Content", f"{extracted.get('alcohol_content', 'N/A')}%")
        st.metric("Net Contents", extracted.get('net_contents', 'Not found'))
    
    # Government warning
    warning_status = "✅ Present" if extracted.get('government_warning_present') else "❌ Missing"
    st.metric("Government Warning", warning_status)
    
    # Confidence score
    extraction_confidence = extracted.get('confidence', 0)
    st.metric("Extraction Confidence", f"{extraction_confidence:.1%}")
    
    # Action buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 Submit Another Label"):
            st.session_state.submission_results = None
            st.rerun()
    with col2:
        if st.button("📊 View All Submissions"):
            st.session_state.page = "admin_history"
            st.rerun()
    with col3:
        if st.button("🏠 Home"):
            st.session_state.page = "home"
            st.rerun()

def render_admin_history():
    """Render admin submission history page"""
    st.header("📊 All Submissions")
    
    # Get all submissions
    session = db_manager.get_session()
    try:
        submissions = session.query(Submission).order_by(Submission.created_at.desc()).all()
        
        if not submissions:
            st.info("No submissions found.")
            return
        
        # Display submissions in a table
        display_data = []
        for submission in submissions:
            display_data.append({
                'ID': submission.id,
                'Brand Name': submission.brand_name,
                'Product Type': submission.product_type,
                'Alcohol Content': f"{submission.alcohol_content}%",
                'Status': submission.status.title(),
                'Created': submission.created_at.strftime('%Y-%m-%d %H:%M')
            })
        
        df = pd.DataFrame(display_data)
        st.dataframe(df, use_container_width=True)
        
        # Filter options
        st.subheader("Filters")
        col1, col2 = st.columns(2)
        
        with col1:
            status_filter = st.selectbox(
                "Filter by Status",
                ['All', 'Matched', 'Mismatched', 'Partial', 'Processing Failed']
            )
        
        with col2:
            if st.button("Apply Filters"):
                # Apply filters (simplified for demo)
                if status_filter != 'All':
                    filtered_df = df[df['Status'].str.contains(status_filter, case=False)]
                    st.dataframe(filtered_df, use_container_width=True)
        
    finally:
        session.close()

def main():
    """Main application function"""
    # Initialize
    init_session_state()
    
    # Validate configuration
    try:
        Config.validate_config()
    except ValueError as e:
        st.error(f"Configuration Error: {e}")
        st.info("Please check your .env file and ensure all required variables are set.")
        return
    
    # Render header
    render_header()
    
    # Render sidebar
    render_sidebar()
    
    # Determine current page
    current_page = st.session_state.get('page', 'home')
    
    # Render main content
    if current_page == 'home':
        if st.session_state.submission_results:
            render_results()
        else:
            render_submission_form()
    elif current_page == 'admin_history':
        render_admin_history()

if __name__ == "__main__":
    main()

