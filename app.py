import streamlit as st
import io
import base64
from datetime import datetime
from PIL import Image
import pandas as pd
import logging

# Import our services and models
from config import Config
from src.models.database import db_manager, User, Submission, VerificationResult, Company, Location
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def init_session_state():
    """Initialize session state variables"""
    if 'user_role' not in st.session_state:
        st.session_state.user_role = Config.DEFAULT_ROLE
    if 'current_user_id' not in st.session_state:
        st.session_state.current_user_id = 1  # Demo user ID
    if 'submission_results' not in st.session_state:
        st.session_state.submission_results = None
    if 'page' not in st.session_state:
        st.session_state.page = 'home'
    if 'selected_submission_id' not in st.session_state:
        st.session_state.selected_submission_id = None

    # Sync state from URL query params for deep-linking and refreshable URLs
    try:
        params = st.query_params  # Streamlit 1.31+
    except Exception:
        # Fallback for older versions
        params = {}

    page_param = params.get('page') if isinstance(params, dict) else params.get('page', None)
    sub_id_param = params.get('id') if isinstance(params, dict) else params.get('id', None)

    if page_param in {'home', 'admin_history', 'submission_detail'}:
        st.session_state.page = page_param
    if sub_id_param:
        try:
            st.session_state.selected_submission_id = int(sub_id_param)
        except (TypeError, ValueError):
            st.session_state.selected_submission_id = None

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
            # Update URL to be refreshable
            try:
                st.query_params.update({'page': 'admin_history'})
            except Exception:
                pass
            st.session_state.page = "admin_history"
            st.rerun()

        if st.sidebar.button("🏢 Manage Companies"):
            try:
                st.query_params.update({'page': 'companies'})
            except Exception:
                pass
            st.session_state.page = "companies"
            st.rerun()
    
    if st.sidebar.button("🏠 Home"):
        try:
            st.query_params.update({'page': 'home'})
        except Exception:
            pass
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
            st.subheader("Organization & Label Images")

            # Company selection / creation
            session = db_manager.get_session()
            try:
                companies = session.query(Company).order_by(Company.name.asc()).all()
            finally:
                session.close()

            company_options = [c.name for c in companies]
            company_map = {c.name: c for c in companies}
            company_options.append("➕ Add new company…")

            selected_company_name = st.selectbox(
                "Company",
                options=company_options,
                help="Select your company. Choose 'Add new company…' if it isn't listed."
            )

            selected_company_id = None

            if selected_company_name == "➕ Add new company…":
                st.info("Use Company Management to create a new company, then return here.")
                st.markdown("[Open Company Management](?page=companies)")
            else:
                selected_company_id = company_map[selected_company_name].id

            # Location selection / creation (depends on selected company or new company later)
            selected_location_id = None
            new_location = {}
            if selected_company_name != "➕ Add new company…":
                session = db_manager.get_session()
                try:
                    locs = session.query(Location).filter(Location.company_id == selected_company_id).order_by(Location.name.asc()).all()
                finally:
                    session.close()
                location_options = [l.name for l in locs]
                location_map = {l.name: l for l in locs}
                location_options.append("➕ Add new location…")

                selected_location_name = st.selectbox(
                    "Location",
                    options=location_options,
                    help="Select the facility/location."
                )
                if selected_location_name == "➕ Add new location…":
                    st.info("Add a new location")
                    coll1, coll2, coll3 = st.columns([2, 1, 1])
                    with coll1:
                        new_location['name'] = st.text_input("Location Name *", placeholder="e.g., Portland Brewery")
                    with coll2:
                        new_location['city'] = st.text_input("City *", placeholder="e.g., Portland")
                    with coll3:
                        new_location['state'] = st.text_input("State *", placeholder="e.g., Oregon")
                    new_location['is_primary'] = st.checkbox("Primary location", value=False)
                else:
                    selected_location_id = location_map[selected_location_name].id
            
            uploaded_files = st.file_uploader(
                "Upload Label Image(s) *",
                type=['jpg', 'jpeg', 'png', 'webp'],
                accept_multiple_files=True,
                help="Upload a photo that includes both front and back labels, or upload separate images capturing all labels."
            )
            
            if uploaded_files:
                # Display previews for all uploaded images
                st.caption(f"Previewing {len(uploaded_files)} image(s)")
                num_cols = 3
                cols = st.columns(num_cols)
                for idx, f in enumerate(uploaded_files):
                    try:
                        img = Image.open(f)
                        with cols[idx % num_cols]:
                            st.image(img, caption=f"Image {idx+1}", width='stretch')
                    except Exception as e:
                        with cols[idx % num_cols]:
                            st.warning(f"Could not preview image {idx+1}: {e}")
        
        # Submit button
        submitted = st.form_submit_button(
            "🔍 Verify Label",
            type="primary",
            use_container_width=True
        )
        
        if submitted:
            # If selecting a company and adding a location, validate
            if selected_company_name != "➕ Add new company…" and selected_location_id is None and not new_location.get('name'):
                st.error("Please select a location or fill out the new location details.")
                return
            if not all([brand_name, product_type, alcohol_content, uploaded_files]):
                st.error("Please fill in all required fields and upload an image.")
            else:
                process_submission(
                    brand_name,
                    product_type,
                    alcohol_content,
                    net_contents,
                    uploaded_files,
                    selected_company_id,
                    selected_location_id,
                    new_location
                )

def process_submission(brand_name, product_type, alcohol_content, net_contents, uploaded_files,
                      selected_company_id, selected_location_id, new_location):
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
            logger.info("Starting submission: brand=%s, product_type=%s, alcohol=%.2f, net_contents=%s",
                        brand_name, product_type, float(alcohol_content), net_contents)
            
            # Ensure location exists when requested
            session = db_manager.get_session()
            try:
                # Create new location if requested
                if selected_location_id is None and new_location.get('name') and selected_company_id:
                    location = Location(
                        company_id=selected_company_id,
                        name=new_location.get('name'),
                        city=new_location.get('city') or '',
                        state=new_location.get('state') or '',
                        is_primary=bool(new_location.get('is_primary'))
                    )
                    session.add(location)
                    session.flush()
                    selected_location_id = location.id
                    logger.info("Created location id=%s for company id=%s", selected_location_id, selected_company_id)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.exception("Error creating company/location: %s", e)
                raise
            finally:
                session.close()

            # Handle one or multiple images
            image_inputs = []
            gcs_urls = []
            skipped = 0
            for f in uploaded_files:
                data = f.read()
                ctype = f.type
                # Skip trivially small/empty files that cause model errors
                if not data or len(data) < 2048:
                    skipped += 1
                    logger.warning("Skipping tiny/empty image: content_type=%s, bytes=%d", ctype, len(data or b''))
                    continue
                image_inputs.append((data, ctype))
                # Upload each image and collect URLs
                url = gcs_service.upload_image(data, content_type=ctype)
                gcs_urls.append(url)
                logger.info("Uploaded image: content_type=%s, bytes=%d, gcs_url=%s", ctype, len(data or b''), url)
            if skipped:
                st.warning(f"Skipped {skipped} tiny image(s) (<2KB). Please ensure images are valid label photos.")
            if not image_inputs:
                st.error("No valid images to process. Please upload clear label images.")
                return
            # Join URLs for storage; first URL is primary
            gcs_url = ";".join(gcs_urls)
            
            # Extract text using Gemini
            extracted_data = gemini_service.extract_label_text(image_inputs)
            logger.info("Gemini extraction result keys: %s", list(extracted_data.keys()) if isinstance(extracted_data, dict) else type(extracted_data))
            logger.info("Extracted: brand=%s, product_type=%s, alcohol=%s, net=%s, warning=%s, confidence=%s",
                        extracted_data.get('brand_name'), extracted_data.get('product_type'),
                        extracted_data.get('alcohol_content'), extracted_data.get('net_contents'),
                        extracted_data.get('government_warning_present'), extracted_data.get('confidence'))
            
            # Verify fields
            verification_results = verification_service.compare_fields(
                form_data, 
                extracted_data
            )
            
            # Get overall status
            overall_status, overall_confidence = verification_service.get_overall_status(verification_results)
            
            # Save to database
            submission_id = save_submission(
                form_data, 
                gcs_url, 
                overall_status, 
                verification_results,
                extracted_data,
                selected_company_id,
                selected_location_id
            )
            
            # Store results in session state
            st.session_state.submission_results = {
                'submission_id': submission_id,
                'form_data': form_data,
                'extracted_data': extracted_data,
                'verification_results': verification_results,
                'overall_status': overall_status,
                'overall_confidence': overall_confidence,
                'image_url': gcs_url
            }
            # Navigate to results page with refreshable URL
            try:
                st.query_params.update({'page': 'results', 'id': str(submission_id)})
            except Exception:
                pass
            st.session_state.page = 'results'
            st.success("Label verification completed!")
            st.rerun()
            
    except Exception as e:
        st.error(f"Error processing submission: {str(e)}")
        st.exception(e)

def save_submission(form_data, gcs_url, status, verification_results, extracted_data, company_id=None, location_id=None):
    """Save submission and results to database and return submission_id"""
    session = db_manager.get_session()
    try:
        # Create submission
        submission = Submission(
            user_id=st.session_state.current_user_id,
            company_id=company_id,
            location_id=location_id,
            brand_name=form_data['brand_name'],
            product_type=form_data['product_type'],
            alcohol_content=form_data['alcohol_content'],
            net_contents=form_data.get('net_contents'),
            image_url=gcs_url,
            status=status
        )
        session.add(submission)
        session.flush()  # Get the ID
        submission_id = submission.id
        
        # Create verification results
        for field_name, result in verification_results.items():
            verification_result = VerificationResult(
                submission_id=submission_id,
                field_name=field_name,
                expected_value=str(result.get('expected', '')),
                extracted_value=str(result.get('extracted', '')),
                match_status=result.get('matched', False),
                confidence_score=result.get('confidence', 0.0),
                details=result.get('details', '')
            )
            session.add(verification_result)
        
        session.commit()
        return submission_id
        
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
    
    # Prepare data for display (cast to strings for Arrow compatibility)
    display_data = []
    for field_name, result in results['verification_results'].items():
        expected_val = result.get('expected', 'N/A')
        extracted_val = result.get('extracted', 'N/A')
        details_val = result.get('details', '')

        display_data.append({
            'Field': field_name.replace('_', ' ').title(),
            'Expected': '' if expected_val is None else str(expected_val),
            'Extracted': '' if extracted_val is None else str(extracted_val),
            'Status': '✅ Match' if result.get('matched') else '❌ Mismatch',
            'Confidence': f"{result.get('confidence', 0):.1%}",
            'Details': '' if details_val is None else str(details_val)
        })
    
    df = pd.DataFrame(display_data)
    st.dataframe(df, width='stretch')
    
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
        # Render as a normal table with clickable rows (links)
        st.subheader("Submissions")
        base_url = "?page=submission_detail&id="
        md_lines = ["| ID | Brand Name | Product Type | Alcohol Content | Status | Created |",
                    "|---:|---|---|---:|---|---|"]
        for row in display_data:
            link = f"[{row['ID']}]({base_url}{row['ID']})"
            md_lines.append(f"| {link} | {row['Brand Name']} | {row['Product Type']} | {row['Alcohol Content']} | {row['Status']} | {row['Created']} |")
        st.markdown("\n".join(md_lines))
        
        # Selection and actions
        # Remove the old selector; rows are clickable via links above

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

def render_submission_detail():
    """Render a detailed view for a selected submission"""
    submission_id = st.session_state.get('selected_submission_id')
    if not submission_id:
        st.info("No submission selected.")
        return
    
    session = db_manager.get_session()
    try:
        submission = session.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            st.error("Submission not found.")
            return
        
        st.header(f"Submission #{submission.id}")
        st.markdown(f"**Brand:** {submission.brand_name}  ")
        st.markdown(f"**Product Type:** {submission.product_type}  ")
        st.markdown(f"**Alcohol Content:** {submission.alcohol_content}%  ")
        st.markdown(f"**Status:** {submission.status.title()}  ")
        st.markdown(f"**Created:** {submission.created_at.strftime('%Y-%m-%d %H:%M')}  ")

        # Show image(s)
        if submission.image_url:
            urls = [u.strip() for u in submission.image_url.split(';') if u.strip()]
            st.subheader("Label Image(s)")
            cols = st.columns(min(3, len(urls))) if urls else []
            for idx, u in enumerate(urls):
                try:
                    img_bytes = gcs_service.get_image_bytes(u)
                    if not img_bytes:
                        raise ValueError("Empty image bytes")
                    with cols[idx % len(cols)]:
                        st.image(img_bytes, caption=f"Image {idx+1}", width='stretch')
                except Exception:
                    # Fallback to a signed URL for private buckets
                    signed = gcs_service.generate_signed_url(u)
                    with cols[idx % len(cols)]:
                        st.image(signed, caption=f"Image {idx+1}", width='stretch')

        # Load verification results
        results = session.query(VerificationResult).filter(VerificationResult.submission_id == submission_id).all()
        if results:
            st.subheader("Field-by-Field Results")
            rows = []
            for r in results:
                rows.append({
                    'Field': r.field_name.replace('_', ' ').title(),
                    'Expected': r.expected_value,
                    'Extracted': r.extracted_value,
                    'Status': '✅ Match' if r.match_status in (True, 'matched', '1') else '❌ Mismatch',
                    'Confidence': f"{(r.confidence_score or 0):.1%}",
                    'Details': r.details or ''
                })
            st.dataframe(pd.DataFrame(rows), width='stretch')

        # Navigation
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Back to Submissions"):
                try:
                    st.query_params.update({'page': 'admin_history'})
                except Exception:
                    pass
                st.session_state.page = "admin_history"
                st.rerun()
        with col2:
            if st.button("🏠 Home"):
                try:
                    st.query_params.update({'page': 'home'})
                except Exception:
                    pass
                st.session_state.page = "home"
                st.rerun()
    finally:
        session.close()

def render_companies():
    """CRUD management for Companies"""
    st.header("🏢 Companies")

    # Query params for edit mode
    try:
        params = st.query_params
    except Exception:
        params = {}
    edit_id = params.get('id') if isinstance(params, dict) else params.get('id', None)
    if edit_id:
        try:
            edit_id = int(edit_id)
        except (TypeError, ValueError):
            edit_id = None

    session = db_manager.get_session()
    try:
        # If an ID is provided, show dedicated edit page
        if edit_id:
            c = session.query(Company).filter(Company.id == edit_id).first()
            if not c:
                st.warning("Company not found.")
            else:
                st.subheader(f"Edit Company #{c.id}")
                with st.form("edit_company_form"):
                    name_e = st.text_input("Name *", value=c.name)
                    ctype_e = st.selectbox("Type *", ["brewery", "winery", "distillery"], index=["brewery","winery","distillery"].index(c.company_type) if c.company_type in ["brewery","winery","distillery"] else 0)
                    is_parent_e = st.checkbox("Is Parent", value=bool(c.is_parent))
                    save = st.form_submit_button("Save Changes")
                    delete = st.form_submit_button("Delete Company")
                    if save and name_e and ctype_e:
                        try:
                            c.name = name_e.strip()
                            c.company_type = ctype_e
                            c.is_parent = bool(is_parent_e)
                            session.commit()
                            st.success("Company updated.")
                            try:
                                st.query_params.update({'page': 'companies', 'id': str(c.id)})
                            except Exception:
                                pass
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Failed to update: {e}")
                    if delete:
                        try:
                            session.delete(c)
                            session.commit()
                            st.success("Company deleted.")
                            try:
                                st.query_params.update({'page': 'companies'})
                            except Exception:
                                pass
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Failed to delete: {e}")

                st.markdown("---")
                st.subheader("Locations")
                locs = session.query(Location).filter(Location.company_id == c.id).order_by(Location.name.asc()).all()
                if locs:
                    md_lines = ["| ID | Name | City | State | Primary | Actions |", "|---:|---|---|---|:---:|---|"]
                    for l in locs:
                        md_lines.append(f"| {l.id} | {l.name} | {l.city or ''} | {l.state or ''} | {'Yes' if l.is_primary else 'No'} | Delete #{l.id} |")
                    st.markdown("\n".join(md_lines))
                    for l in locs:
                        if st.button("Delete", key=f"delete_loc_{l.id}"):
                            try:
                                session.delete(l)
                                session.commit()
                                st.success(f"Deleted location #{l.id}")
                                try:
                                    st.query_params.update({'page': 'companies', 'id': str(c.id)})
                                except Exception:
                                    pass
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Failed to delete location: {e}")
                else:
                    st.info("No locations yet.")

                st.markdown("### Add Location")
                with st.form("add_location_to_company", clear_on_submit=True):
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        lname = st.text_input("Name *")
                    with col2:
                        lcity = st.text_input("City")
                    with col3:
                        lstate = st.text_input("State")
                    with col4:
                        lprimary = st.checkbox("Primary", value=False)
                    add_loc = st.form_submit_button("Add Location")
                    if add_loc and lname:
                        try:
                            loc = Location(
                                company_id=c.id,
                                name=lname.strip(),
                                city=(lcity or '').strip(),
                                state=(lstate or '').strip(),
                                is_primary=bool(lprimary)
                            )
                            session.add(loc)
                            session.commit()
                            st.success("Location added.")
                            try:
                                st.query_params.update({'page': 'companies', 'id': str(c.id)})
                            except Exception:
                                pass
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Failed to add location: {e}")

                st.markdown("---")
                if st.button("⬅️ Back to Companies List"):
                    try:
                        st.query_params.update({'page': 'companies'})
                    except Exception:
                        pass
                    st.rerun()

        else:
            # Companies list + create page
            companies = session.query(Company).order_by(Company.name.asc()).all()
            rows = []
            for c in companies:
                rows.append({
                    'ID': c.id,
                    'Name': c.name,
                    'Type': c.company_type,
                    'Is Parent': 'Yes' if c.is_parent else 'No',
                    'Created': c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else ''
                })
            st.subheader("All Companies")
            if rows:
                md_lines = ["| ID | Name | Type | Parent | Created |", "|---:|---|---|:---:|---|"]
                base_url = "?page=companies&id="
                for r in rows:
                    link = f"[{r['ID']}]({base_url}{r['ID']})"
                    md_lines.append(f"| {link} | {r['Name']} | {r['Type']} | {r['Is Parent']} | {r['Created']} |")
                st.markdown("\n".join(md_lines))
            else:
                st.info("No companies yet.")

            st.markdown("---")
            st.subheader("Create Company")
            with st.form("create_company_form", clear_on_submit=True):
                name = st.text_input("Name *")
                ctype = st.selectbox("Type *", ["brewery", "winery", "distillery"])
                is_parent = st.checkbox("Is Parent", value=True)
                submitted = st.form_submit_button("Create Company")
                if submitted and name and ctype:
                    try:
                        company = Company(name=name.strip(), company_type=ctype, is_parent=is_parent)
                        session.add(company)
                        session.commit()
                        st.success(f"Created company '{name}'.")
                        try:
                            st.query_params.update({'page': 'companies'})
                        except Exception:
                            pass
                        st.rerun()
                    except Exception as e:
                        session.rollback()
                        st.error(f"Failed to create company: {e}")

            st.markdown("---")
            if st.button("⬅️ Back to Submission Form"):
                try:
                    st.query_params.update({'page': 'home'})
                except Exception:
                    pass
                st.session_state.page = 'home'
                st.rerun()
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
        render_submission_form()
    elif current_page == 'admin_history':
        render_admin_history()
    elif current_page == 'submission_detail':
        render_submission_detail()
    elif current_page == 'results':
        render_results()
    elif current_page == 'companies':
        render_companies()

if __name__ == "__main__":
    main()

