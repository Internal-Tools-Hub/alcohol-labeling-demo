from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import Config

Base = declarative_base()

class Company(Base):
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    company_type = Column(String(50), nullable=False)  # 'brewery', 'winery', 'distillery'
    parent_company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    is_parent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    parent_company = relationship("Company", remote_side=[id], back_populates="subsidiaries")
    subsidiaries = relationship("Company", back_populates="parent_company")
    locations = relationship("Location", back_populates="company")
    users = relationship("User", back_populates="company")
    submissions = relationship("Submission", back_populates="company")

class Location(Base):
    __tablename__ = 'locations'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    name = Column(String(255), nullable=False)  # e.g., "Portland Brewery", "Napa Winery"
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False, default='USA')
    address = Column(Text, nullable=True)
    is_primary = Column(Boolean, default=False)  # Primary location for the company
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="locations")
    submissions = relationship("Submission", back_populates="location")

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    role = Column(String(50), default='submitter')  # 'submitter' or 'admin'
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="users")
    submissions = relationship("Submission", back_populates="user")

class Submission(Base):
    __tablename__ = 'submissions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    brand_name = Column(String(255), nullable=False)
    product_type = Column(String(255), nullable=False)
    alcohol_content = Column(Float, nullable=False)
    net_contents = Column(String(100), nullable=True)
    image_url = Column(String(500), nullable=False)
    status = Column(String(50), default='pending')  # 'pending', 'matched', 'mismatched', 'processing_failed'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="submissions")
    company = relationship("Company", back_populates="submissions")
    location = relationship("Location", back_populates="submissions")
    verification_results = relationship("VerificationResult", back_populates="submission")

class VerificationResult(Base):
    __tablename__ = 'verification_results'
    
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=False)
    field_name = Column(String(100), nullable=False)  # 'brand_name', 'product_type', 'alcohol_content', etc.
    expected_value = Column(Text, nullable=False)
    extracted_value = Column(Text, nullable=False)
    match_status = Column(String(50), nullable=False)  # 'matched', 'mismatched', 'not_found'
    confidence_score = Column(Float, nullable=True)  # For fuzzy matching scores
    details = Column(Text, nullable=True)  # Additional details about the match/mismatch
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    submission = relationship("Submission", back_populates="verification_results")

class DatabaseManager:
    def __init__(self):
        self.engine = create_engine(Config.DATABASE_URL)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def create_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def init_demo_data(self):
        """Initialize demo data for testing"""
        session = self.get_session()
        try:
            # Create parent companies
            parent_companies = [
                {
                    'name': 'Golden Valley Brewing Group',
                    'company_type': 'brewery',
                    'is_parent': True,
                    'locations': [
                        {'name': 'Portland Brewery', 'city': 'Portland', 'state': 'Oregon', 'is_primary': True},
                        {'name': 'Denver Brewery', 'city': 'Denver', 'state': 'Colorado', 'is_primary': False},
                        {'name': 'Seattle Brewery', 'city': 'Seattle', 'state': 'Washington', 'is_primary': False}
                    ]
                },
                {
                    'name': 'Vineyard Estate Wine Group',
                    'company_type': 'winery',
                    'is_parent': True,
                    'locations': [
                        {'name': 'Napa Valley Winery', 'city': 'Napa', 'state': 'California', 'is_primary': True},
                        {'name': 'Sonoma Winery', 'city': 'Sonoma', 'state': 'California', 'is_primary': False},
                        {'name': 'Willamette Valley Winery', 'city': 'McMinnville', 'state': 'Oregon', 'is_primary': False}
                    ]
                },
                {
                    'name': 'Golden Oak Spirits Group',
                    'company_type': 'distillery',
                    'is_parent': True,
                    'locations': [
                        {'name': 'Louisville Distillery', 'city': 'Louisville', 'state': 'Kentucky', 'is_primary': True},
                        {'name': 'Bardstown Distillery', 'city': 'Bardstown', 'state': 'Kentucky', 'is_primary': False},
                        {'name': 'Nashville Distillery', 'city': 'Nashville', 'state': 'Tennessee', 'is_primary': False}
                    ]
                }
            ]
            
            for company_data in parent_companies:
                # Check if company exists
                existing_company = session.query(Company).filter(
                    Company.name == company_data['name']
                ).first()
                
                if not existing_company:
                    company = Company(
                        name=company_data['name'],
                        company_type=company_data['company_type'],
                        is_parent=company_data['is_parent']
                    )
                    session.add(company)
                    session.flush()  # Get the company ID
                    
                    # Add locations
                    for loc_data in company_data['locations']:
                        location = Location(
                            company_id=company.id,
                            name=loc_data['name'],
                            city=loc_data['city'],
                            state=loc_data['state'],
                            is_primary=loc_data['is_primary']
                        )
                        session.add(location)
                    
                    print(f"Created company: {company_data['name']}")
                else:
                    print(f"Company already exists: {company_data['name']}")
            
            # Create demo users for each company
            demo_users = [
                {'email': 'admin@goldenvalley.com', 'role': 'admin', 'company_name': 'Golden Valley Brewing Group'},
                {'email': 'admin@vineyardestate.com', 'role': 'admin', 'company_name': 'Vineyard Estate Wine Group'},
                {'email': 'admin@goldenoak.com', 'role': 'admin', 'company_name': 'Golden Oak Spirits Group'},
                {'email': 'demo@example.com', 'role': 'admin', 'company_name': 'Golden Valley Brewing Group'}  # Default demo user
            ]
            
            for user_data in demo_users:
                existing_user = session.query(User).filter(User.email == user_data['email']).first()
                if not existing_user:
                    company = session.query(Company).filter(Company.name == user_data['company_name']).first()
                    if company:
                        user = User(
                            email=user_data['email'],
                            role=user_data['role'],
                            company_id=company.id
                        )
                        session.add(user)
                        print(f"Created user: {user_data['email']}")
                    else:
                        print(f"Company not found for user: {user_data['email']}")
                else:
                    print(f"User already exists: {user_data['email']}")
            
            session.commit()
            print("Demo data initialization complete")
            
        except Exception as e:
            print(f"Error creating demo data: {e}")
            session.rollback()
        finally:
            session.close()
    
    def get_company_locations(self, company_id):
        """Get all locations for a specific company"""
        session = self.get_session()
        try:
            locations = session.query(Location).filter(Location.company_id == company_id).all()
            return locations
        finally:
            session.close()
    
    def get_user_company(self, user_id):
        """Get the company for a specific user"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user and user.company_id:
                company = session.query(Company).filter(Company.id == user.company_id).first()
                return company
            return None
        finally:
            session.close()

# Global database manager instance
db_manager = DatabaseManager()
