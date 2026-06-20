-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables if they exist
DROP TABLE IF EXISTS progress CASCADE;
DROP TABLE IF EXISTS teams CASCADE;

-- Create Teams table
CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    team_name VARCHAR(255) NOT NULL UNIQUE,
    leader_name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    current_level INTEGER DEFAULT 1,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completion_time TIMESTAMP WITH TIME ZONE,
    completed BOOLEAN DEFAULT FALSE,
    winner_status BOOLEAN DEFAULT FALSE,
    score INTEGER DEFAULT 0
);

-- Create Progress table to enforce QR code scanning progression
CREATE TABLE progress (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    qr_id INTEGER NOT NULL,
    scanned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team_id, qr_id)
);
