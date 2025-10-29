import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from src.models.database import db_manager, Submission, VerificationResult, User

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
        col1, col2, col3 = st.columns(3)
        
        with col1:
            status_filter = st.selectbox(
                "Filter by Status",
                ['All', 'Matched', 'Mismatched', 'Partial', 'Processing Failed']
            )
        
        with col2:
            date_filter = st.selectbox(
                "Filter by Date",
                ['All', 'Today', 'Last 7 days', 'Last 30 days']
            )
        
        with col3:
            if st.button("Apply Filters"):
                # Apply status filter
                if status_filter != 'All':
                    df = df[df['Status'].str.contains(status_filter, case=False)]
                
                # Apply date filter
                if date_filter != 'All':
                    now = datetime.now()
                    if date_filter == 'Today':
                        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    elif date_filter == 'Last 7 days':
                        start_date = now - timedelta(days=7)
                    elif date_filter == 'Last 30 days':
                        start_date = now - timedelta(days=30)
                    
                    # Convert Created column to datetime for filtering
                    df['Created'] = pd.to_datetime(df['Created'])
                    df = df[df['Created'] >= start_date]
                
                st.dataframe(df, use_container_width=True)
        
        # Detailed view for selected submission
        st.subheader("Detailed View")
        selected_id = st.selectbox(
            "Select Submission ID for Details",
            options=df['ID'].tolist(),
            index=0
        )
        
        if selected_id:
            show_submission_details(selected_id)
        
    finally:
        session.close()

def show_submission_details(submission_id):
    """Show detailed information for a specific submission"""
    session = db_manager.get_session()
    try:
        # Get submission
        submission = session.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            st.error("Submission not found.")
            return
        
        # Display submission info
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Brand Name", submission.brand_name)
            st.metric("Product Type", submission.product_type)
            st.metric("Alcohol Content", f"{submission.alcohol_content}%")
        
        with col2:
            st.metric("Net Contents", submission.net_contents or "Not specified")
            st.metric("Status", submission.status.title())
            st.metric("Created", submission.created_at.strftime('%Y-%m-%d %H:%M:%S'))
        
        # Get verification results
        verification_results = session.query(VerificationResult).filter(
            VerificationResult.submission_id == submission_id
        ).all()
        
        if verification_results:
            st.subheader("Verification Results")
            
            # Prepare data for display
            results_data = []
            for result in verification_results:
                results_data.append({
                    'Field': result.field_name.replace('_', ' ').title(),
                    'Expected': result.expected_value,
                    'Extracted': result.extracted_value,
                    'Status': '✅ Match' if result.match_status else '❌ Mismatch',
                    'Confidence': f"{result.confidence_score:.1%}",
                    'Details': result.details
                })
            
            results_df = pd.DataFrame(results_data)
            st.dataframe(results_df, use_container_width=True)
        
        # Image display
        if submission.image_url:
            st.subheader("Label Image")
            try:
                from src.services.gcs_service import gcs_service
                image_bytes = gcs_service.get_image_bytes(submission.image_url)
                st.image(image_bytes, caption=f"Label for {submission.brand_name}", use_column_width=True)
            except Exception as e:
                st.error(f"Could not load image: {e}")
        
    finally:
        session.close()

if __name__ == "__main__":
    render_admin_history()

