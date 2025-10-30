-- Alcohol Label Verification Database Schema
-- This script creates the necessary tables for the application

-- Create companies table (for organizational structure)
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    company_type VARCHAR(50) NOT NULL, -- 'brewery', 'winery', 'distillery'
    parent_company_id INTEGER NULL REFERENCES companies(id),
    is_parent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create locations table (company sites)
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL DEFAULT 'USA',
    address TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) DEFAULT 'submitter',
    company_id INTEGER NULL REFERENCES companies(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create submissions table
CREATE TABLE IF NOT EXISTS submissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    company_id INTEGER NULL REFERENCES companies(id),
    location_id INTEGER NULL REFERENCES locations(id),
    brand_name VARCHAR(255) NOT NULL,
    product_type VARCHAR(255) NOT NULL,
    alcohol_content FLOAT NOT NULL,
    net_contents VARCHAR(100),
    image_url VARCHAR(500) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create verification_results table
CREATE TABLE IF NOT EXISTS verification_results (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES submissions(id),
    field_name VARCHAR(100) NOT NULL,
    expected_value TEXT NOT NULL,
    extracted_value TEXT NOT NULL,
    match_status VARCHAR(50) NOT NULL,
    confidence_score FLOAT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_company_id ON submissions(company_id);
CREATE INDEX IF NOT EXISTS idx_submissions_location_id ON submissions(location_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);
CREATE INDEX IF NOT EXISTS idx_verification_results_submission_id ON verification_results(submission_id);
CREATE INDEX IF NOT EXISTS idx_verification_results_field_name ON verification_results(field_name);

-- Seed minimal demo data
INSERT INTO companies (name, company_type, is_parent)
VALUES ('Golden Valley Brewing Group', 'brewery', TRUE)
ON CONFLICT DO NOTHING;

-- Ensure a primary location exists
INSERT INTO locations (company_id, name, city, state, is_primary)
SELECT id, 'Portland Brewery', 'Portland', 'Oregon', TRUE FROM companies
WHERE name = 'Golden Valley Brewing Group'
ON CONFLICT DO NOTHING;

-- Insert demo user linked to company (optional)
INSERT INTO users (email, role, company_id)
SELECT 'demo@example.com', 'admin', id FROM companies
WHERE name = 'Golden Valley Brewing Group'
ON CONFLICT (email) DO NOTHING;

