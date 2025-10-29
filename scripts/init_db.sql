-- Alcohol Label Verification Database Schema
-- This script creates the necessary tables for the application

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) DEFAULT 'submitter',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create submissions table
CREATE TABLE IF NOT EXISTS submissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
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
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);
CREATE INDEX IF NOT EXISTS idx_verification_results_submission_id ON verification_results(submission_id);
CREATE INDEX IF NOT EXISTS idx_verification_results_field_name ON verification_results(field_name);

-- Insert demo user
INSERT INTO users (email, role) VALUES ('demo@example.com', 'admin') 
ON CONFLICT (email) DO NOTHING;

