"""
API endpoints for managing company locations and submissions
"""
from flask import Blueprint, request, jsonify
from src.models.database import db_manager
from sqlalchemy.orm import sessionmaker

location_api = Blueprint('location_api', __name__)

@location_api.route('/api/companies/<int:company_id>/locations', methods=['GET'])
def get_company_locations(company_id):
    """Get all locations for a specific company"""
    try:
        locations = db_manager.get_company_locations(company_id)
        location_list = []
        for location in locations:
            location_list.append({
                'id': location.id,
                'name': location.name,
                'city': location.city,
                'state': location.state,
                'country': location.country,
                'is_primary': location.is_primary,
                'full_address': f"{location.name}, {location.city}, {location.state}"
            })
        return jsonify({'locations': location_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@location_api.route('/api/users/<int:user_id>/company', methods=['GET'])
def get_user_company(user_id):
    """Get the company for a specific user"""
    try:
        company = db_manager.get_user_company(user_id)
        if company:
            return jsonify({
                'id': company.id,
                'name': company.name,
                'company_type': company.company_type,
                'is_parent': company.is_parent
            })
        return jsonify({'error': 'Company not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@location_api.route('/api/submissions', methods=['POST'])
def create_submission():
    """Create a new submission with company and location"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['user_id', 'company_id', 'location_id', 'brand_name', 
                          'product_type', 'alcohol_content', 'image_url']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create submission
        session = db_manager.get_session()
        try:
            from src.models.database import Submission
            submission = Submission(
                user_id=data['user_id'],
                company_id=data['company_id'],
                location_id=data['location_id'],
                brand_name=data['brand_name'],
                product_type=data['product_type'],
                alcohol_content=data['alcohol_content'],
                net_contents=data.get('net_contents'),
                image_url=data['image_url']
            )
            session.add(submission)
            session.commit()
            
            return jsonify({
                'id': submission.id,
                'status': submission.status,
                'message': 'Submission created successfully'
            }), 201
        finally:
            session.close()
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@location_api.route('/api/submissions/<int:submission_id>', methods=['GET'])
def get_submission(submission_id):
    """Get submission details with company and location info"""
    try:
        session = db_manager.get_session()
        try:
            from src.models.database import Submission, Company, Location, User
            
            submission = session.query(Submission).filter(Submission.id == submission_id).first()
            if not submission:
                return jsonify({'error': 'Submission not found'}), 404
            
            return jsonify({
                'id': submission.id,
                'brand_name': submission.brand_name,
                'product_type': submission.product_type,
                'alcohol_content': submission.alcohol_content,
                'net_contents': submission.net_contents,
                'status': submission.status,
                'created_at': submission.created_at.isoformat(),
                'company': {
                    'id': submission.company.id,
                    'name': submission.company.name,
                    'company_type': submission.company.company_type
                },
                'location': {
                    'id': submission.location.id,
                    'name': submission.location.name,
                    'city': submission.location.city,
                    'state': submission.location.state,
                    'country': submission.location.country
                },
                'user': {
                    'id': submission.user.id,
                    'email': submission.user.email,
                    'role': submission.user.role
                }
            })
        finally:
            session.close()
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

