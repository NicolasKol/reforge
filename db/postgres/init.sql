-- =============================================================================
-- Reforge - PostgreSQL Initialization Script
-- Core tables for n8n and basic project structure
-- =============================================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search on symbols

-- =============================================================================
-- Note: n8n will create its own tables automatically on first run.
-- This script sets up additional tables for the reforge provenance layer.
-- =============================================================================

-- Create schema for reforge-specific tables (separate from n8n's public schema)
CREATE SCHEMA IF NOT EXISTS reforge;

-- Note: User permissions will be granted after user creation
-- The POSTGRES_USER from docker-compose will be created automatically
