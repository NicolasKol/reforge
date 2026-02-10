-- =============================================================================
-- NUKE Reforge Data & Schema (Preserves n8n in public schema)
-- =============================================================================
-- This script completely destroys all reforge provenance data and tables
-- while leaving n8n's workflow engine data intact in the public schema.
--
-- WARNING: This is destructive and irreversible.
-- =============================================================================

\echo '  WARNING: This will DELETE ALL reforge data!'
\echo '    - All synthetic code records'
\echo '    - All binaries and build artifacts'
\echo '    - All experiments, evaluations, and LLM interactions'
\echo '    - All function metadata and call graphs'
\echo ''
\echo '✓  Will PRESERVE:'
\echo '    - All n8n workflows, executions, and credentials (public schema)'
\echo ''
\echo 'Press Ctrl+C to abort, or press Enter to continue...'
\prompt 'Type YES to confirm deletion: ' confirmation

-- Abort if not confirmed
\if :{?confirmation}
    \if :confirmation != 'YES'
        \echo 'Aborting...'
        \q
    \endif
\else
    \echo 'Aborting...'
    \q
\endif

\echo ''
\echo ' Nuking reforge schema...'

-- =============================================================================
-- Drop all reforge tables (preserves public schema)
-- =============================================================================

-- Drop tables in dependency order (children first)
DROP TABLE IF EXISTS reforge.call_graph_edges CASCADE;
DROP TABLE IF EXISTS reforge.functions CASCADE;
DROP TABLE IF EXISTS reforge.decompilation_results CASCADE;
DROP TABLE IF EXISTS reforge.evaluation_metrics CASCADE;
DROP TABLE IF EXISTS reforge.llm_interactions CASCADE;
DROP TABLE IF EXISTS reforge.binaries CASCADE;
DROP TABLE IF EXISTS reforge.build_jobs CASCADE;
DROP TABLE IF EXISTS reforge.synthetic_code CASCADE;
DROP TABLE IF EXISTS reforge.experiments CASCADE;
DROP TABLE IF EXISTS reforge.prompt_templates CASCADE;

-- Drop any other reforge tables that might exist
-- (Add more as needed)

\echo '✓  All reforge tables dropped'

-- =============================================================================
-- Optional: Drop and recreate schema for clean slate
-- =============================================================================

-- Uncomment to completely drop the schema:
-- DROP SCHEMA IF EXISTS reforge CASCADE;
-- CREATE SCHEMA reforge;
-- GRANT ALL PRIVILEGES ON SCHEMA reforge TO reforge_user;

\echo ''
\echo ' Reforge data nuked successfully!'
\echo ''
\echo 'To rebuild schema, run:'
\echo '  \\i /docker-entrypoint-initdb.d/02-provenance.sql'
\echo ''
\echo 'Or from host (PowerShell):'
\echo '  Get-Content db/postgres/provenance.sql | docker exec -i reforge-postgres psql -U reforge_user -d reforge'
\echo ''
\echo 'Or from host (bash/sh):'
\echo '  docker exec -i reforge-postgres psql -U reforge_user -d reforge < db/postgres/provenance.sql'
    