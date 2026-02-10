-- =============================================================================
-- Reforge - Provenance Schema (builder_synth_v1)
-- Minimal schema for synthetic code builds and binary artifacts
-- =============================================================================

SET search_path TO reforge, public;

-- =============================================================================
-- Synthetic Code — builder_synth_v1
-- Multi-file synthetic C test cases with snapshot-level identity.
-- =============================================================================
CREATE TABLE IF NOT EXISTS synthetic_code (
    id UUID PRIMARY KEY DEFAULT public.uuid_generate_v4(),

    -- Identity
    name VARCHAR(255) UNIQUE NOT NULL,
    test_category VARCHAR(100) NOT NULL,  -- arrays, loops, strings, functions, etc.
    language VARCHAR(50) DEFAULT 'c',     -- only 'c' in v1

    -- Source snapshot (multi-file)
    snapshot_sha256 VARCHAR(64) NOT NULL,  -- hash over normalized archive of all source files
    file_count INT DEFAULT 1,              -- number of source files
    source_files JSONB DEFAULT '[]',       -- [{path_rel, sha256, size_bytes, role}, ...]

    -- Build status
    status VARCHAR(50) DEFAULT 'QUEUED',   -- QUEUED, BUILDING, SUCCESS, PARTIAL, FAILED

    -- Extensible metadata (receipt summary, toolchain, etc.)
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_synthetic_category ON synthetic_code(test_category);
CREATE INDEX idx_synthetic_name ON synthetic_code(name);
CREATE INDEX idx_synthetic_status ON synthetic_code(status);

-- =============================================================================
-- Binaries — builder_synth_v1
-- ELF artifacts produced by synthetic builds.
-- =============================================================================
CREATE TABLE IF NOT EXISTS binaries (
    id UUID PRIMARY KEY DEFAULT public.uuid_generate_v4(),

    -- Identification
    file_path TEXT NOT NULL,                   -- Local filesystem path
    file_hash VARCHAR(64) UNIQUE NOT NULL,     -- SHA256 of binary file
    file_size BIGINT,

    -- Build provenance
    synthetic_code_id UUID NOT NULL REFERENCES synthetic_code(id) ON DELETE CASCADE,

    -- Build configuration
    compiler VARCHAR(50) DEFAULT 'gcc',        -- gcc only in v1
    optimization_level VARCHAR(10) NOT NULL,   -- O0, O1, O2, O3
    variant_type VARCHAR(20) NOT NULL,         -- debug, release, stripped

    -- Binary properties
    architecture VARCHAR(50) DEFAULT 'x86_64',
    has_debug_info BOOLEAN DEFAULT FALSE,
    is_stripped BOOLEAN DEFAULT FALSE,

    -- ELF metadata (type, arch, build-id)
    elf_metadata JSONB DEFAULT '{}',

    -- Extensible metadata (flags, cell status, etc.)
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_binaries_synthetic ON binaries(synthetic_code_id);
CREATE INDEX idx_binaries_hash ON binaries(file_hash);
CREATE INDEX idx_binaries_variant ON binaries(variant_type);
CREATE INDEX idx_binaries_optimization ON binaries(optimization_level);
