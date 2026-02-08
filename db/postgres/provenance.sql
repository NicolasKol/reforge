-- =============================================================================
-- Reforge - Provenance & Metadata Tracking Schema
-- Tracks all LLM interactions, decompilation artifacts, and experiment metrics
-- =============================================================================

SET search_path TO reforge, public;

-- =============================================================================
-- Build Jobs - Track C/C++ project builds
-- =============================================================================
CREATE TABLE IF NOT EXISTS build_jobs (
    id UUID PRIMARY KEY DEFAULT public.uuid_generate_v4(),
    
    -- Source
    repo_url VARCHAR(500),  -- Git URL (null for synthetic builds)
    commit_ref VARCHAR(255),  -- Branch/tag/commit
    commit_hash VARCHAR(64),  -- Actual commit SHA
    
    -- Configuration
    compiler VARCHAR(50) NOT NULL,  -- gcc, clang
    compiler_version VARCHAR(50),  -- e.g., "11.4.0"
    optimizations JSONB NOT NULL,  -- ["O0", "O2", "O3"]
    
    -- Status
    status VARCHAR(50) DEFAULT 'QUEUED',  -- QUEUED, BUILDING, SUCCESS, FAILED, TIMEOUT
    error_message TEXT,
    build_log TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_build_jobs_status ON build_jobs(status);
CREATE INDEX idx_build_jobs_created ON build_jobs(created_at);
CREATE INDEX idx_build_jobs_repo ON build_jobs(repo_url);

-- =============================================================================
-- Synthetic Code - For synthetic/hand-crafted test cases
-- =============================================================================
CREATE TABLE IF NOT EXISTS synthetic_code (
    id UUID PRIMARY KEY DEFAULT public.uuid_generate_v4(),
    
    -- Source
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    source_code TEXT NOT NULL,
    source_hash VARCHAR(64) NOT NULL,  -- SHA256 of source code
    language VARCHAR(50) DEFAULT 'c',  -- c, cpp
    
    -- Metadata
    complexity_level VARCHAR(50),  -- simple, medium, complex
    test_category VARCHAR(100) NOT NULL,  -- arrays, loops, strings, functions, etc.
    ground_truth JSONB DEFAULT '{}',  -- Known correct variable names, types, etc.
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_synthetic_category ON synthetic_code(test_category);
CREATE INDEX idx_synthetic_name ON synthetic_code(name);

-- =============================================================================
-- Binary Analysis Targets
-- =============================================================================
CREATE TABLE IF NOT EXISTS binaries (
    id UUID PRIMARY KEY DEFAULT public.uuid_generate_v4(),
    
    -- Identification
    file_path TEXT NOT NULL,  -- Local filesystem path
    file_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA256 of binary file
    file_size BIGINT,
    
    -- Build Provenance
    build_job_id UUID REFERENCES build_jobs(id) ON DELETE SET NULL,
    synthetic_code_id UUID REFERENCES synthetic_code(id) ON DELETE SET NULL,
    
    -- Build Configuration
    compiler VARCHAR(50),  -- gcc, clang
    compiler_version VARCHAR(50),
    optimization_level VARCHAR(10),  -- O0, O1, O2, O3, Os
    
    -- Binary Properties
    architecture VARCHAR(50) DEFAULT 'x86_64',  -- x86, x86_64, ARM, etc.
    
    -- Debug Info & Variants
    has_debug_info BOOLEAN DEFAULT FALSE,
    is_stripped BOOLEAN DEFAULT FALSE,
    variant_type VARCHAR(20),  -- 'debug', 'release', 'stripped'
    debug_sections JSONB DEFAULT '[]',  -- [".debug_info", ".debug_line", ...]
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraint: binary must be from either a build job OR synthetic code, not both
    CONSTRAINT binary_source_check CHECK (
        (build_job_id IS NOT NULL AND synthetic_code_id IS NULL) OR
        (build_job_id IS NULL AND synthetic_code_id IS NOT NULL)
    )
);

CREATE INDEX idx_binaries_build_job ON binaries(build_job_id);
CREATE INDEX idx_binaries_synthetic ON binaries(synthetic_code_id);
CREATE INDEX idx_binaries_hash ON binaries(file_hash);
CREATE INDEX idx_binaries_variant ON binaries(variant_type);
CREATE INDEX idx_binaries_optimization ON binaries(optimization_level);
CREATE INDEX idx_binaries_arch ON binaries(architecture);

-- =============================================================================
-- Functions Extracted from Binaries
-- =============================================================================
CREATE TABLE IF NOT EXISTS functions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    binary_id UUID REFERENCES binaries(id) ON DELETE CASCADE,
    address VARCHAR(20) NOT NULL,  -- Hex address
    name VARCHAR(255),  -- Recovered or original name
    decompiled_code TEXT,  -- Ghidra/IDA output
    pcode TEXT,  -- Intermediate representation
    llvm_ir TEXT,  -- Lifted LLVM IR if available
    signature VARCHAR(500),  -- Function signature
    calling_convention VARCHAR(50),
    is_library_function BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(binary_id, address)
);

CREATE INDEX idx_functions_binary ON functions(binary_id);
CREATE INDEX idx_functions_name ON functions(name);

-- =============================================================================
-- LLM Prompts & Templates
-- =============================================================================
CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    version INT DEFAULT 1,
    category VARCHAR(100),  -- decompilation, variable_naming, type_recovery, etc.
    system_prompt TEXT,
    user_prompt_template TEXT NOT NULL,
    few_shot_examples JSONB DEFAULT '[]',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_prompts_category ON prompt_templates(category);

-- =============================================================================
-- LLM Interactions Log (Provenance Core)
-- =============================================================================
CREATE TABLE IF NOT EXISTS llm_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id VARCHAR(255),  -- n8n execution ID for traceability
    workflow_id VARCHAR(255),  -- n8n workflow ID
    function_id UUID REFERENCES functions(id) ON DELETE SET NULL,
    prompt_template_id UUID REFERENCES prompt_templates(id) ON DELETE SET NULL,
    
    -- Model Configuration
    model_provider VARCHAR(50) NOT NULL,  -- openai, anthropic, ollama, etc.
    model_name VARCHAR(100) NOT NULL,  -- gpt-4, claude-3-opus, llama-3, etc.
    model_config JSONB DEFAULT '{}',  -- temperature, max_tokens, etc.
    
    -- Input/Output
    input_context TEXT,  -- What was sent to the model
    full_prompt TEXT,  -- Complete rendered prompt
    raw_response TEXT,  -- Raw model output
    parsed_output JSONB,  -- Structured extraction from response
    
    -- Metrics
    input_tokens INT,
    output_tokens INT,
    latency_ms INT,
    cost_usd DECIMAL(10, 6),
    
    -- Status
    status VARCHAR(50) DEFAULT 'completed',  -- completed, error, timeout
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_llm_execution ON llm_interactions(execution_id);
CREATE INDEX idx_llm_function ON llm_interactions(function_id);
CREATE INDEX idx_llm_model ON llm_interactions(model_provider, model_name);
CREATE INDEX idx_llm_created ON llm_interactions(created_at);

-- =============================================================================
-- Decompilation Results
-- =============================================================================
CREATE TABLE IF NOT EXISTS decompilation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    function_id UUID REFERENCES functions(id) ON DELETE CASCADE,
    llm_interaction_id UUID REFERENCES llm_interactions(id) ON DELETE SET NULL,
    
    -- Output
    generated_code TEXT NOT NULL,
    language VARCHAR(50) DEFAULT 'C',
    
    -- Recovered Semantics
    recovered_variables JSONB DEFAULT '[]',  -- [{original: "var_8", recovered: "counter", type: "int"}]
    recovered_types JSONB DEFAULT '[]',
    recovered_function_name VARCHAR(255),
    
    -- Validation Status
    compiles BOOLEAN,
    compilation_errors TEXT,
    asan_clean BOOLEAN,
    asan_errors TEXT,
    
    -- Iteration tracking
    iteration_number INT DEFAULT 1,
    is_final BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_decompilation_function ON decompilation_results(function_id);
CREATE INDEX idx_decompilation_compiles ON decompilation_results(compiles);

-- =============================================================================
-- Experiment Runs
-- =============================================================================
CREATE TABLE IF NOT EXISTS experiments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Configuration snapshot
    config JSONB NOT NULL,  -- Full experiment configuration
    workflow_version VARCHAR(100),
    
    -- Scope
    binary_ids UUID[] DEFAULT '{}',
    function_count INT,
    
    -- Status
    status VARCHAR(50) DEFAULT 'running',  -- running, completed, failed, cancelled
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results Summary
    metrics JSONB DEFAULT '{}'  -- Aggregated metrics
);

CREATE INDEX idx_experiments_status ON experiments(status);

-- =============================================================================
-- Evaluation Metrics
-- =============================================================================
CREATE TABLE IF NOT EXISTS evaluation_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    experiment_id UUID REFERENCES experiments(id) ON DELETE CASCADE,
    decompilation_id UUID REFERENCES decompilation_results(id) ON DELETE CASCADE,
    
    -- Metrics
    codebleu_score DECIMAL(5, 4),
    exact_match BOOLEAN,
    variable_accuracy DECIMAL(5, 4),
    type_accuracy DECIMAL(5, 4),
    compilation_success BOOLEAN,
    functional_equivalence BOOLEAN,
    
    -- Custom metrics as JSON for flexibility
    custom_metrics JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_metrics_experiment ON evaluation_metrics(experiment_id);

-- =============================================================================
-- Function Call Graph
-- =============================================================================
CREATE TABLE IF NOT EXISTS call_graph_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    binary_id UUID REFERENCES binaries(id) ON DELETE CASCADE,
    caller_id UUID REFERENCES functions(id) ON DELETE CASCADE,
    callee_id UUID REFERENCES functions(id) ON DELETE CASCADE,
    call_site_address VARCHAR(20),
    call_type VARCHAR(50),  -- direct, indirect, virtual
    UNIQUE(caller_id, callee_id, call_site_address)
);

CREATE INDEX idx_callgraph_binary ON call_graph_edges(binary_id);
CREATE INDEX idx_callgraph_caller ON call_graph_edges(caller_id);
CREATE INDEX idx_callgraph_callee ON call_graph_edges(callee_id);

-- =============================================================================
-- Helper Views
-- =============================================================================

-- Latest decompilation per function
CREATE OR REPLACE VIEW latest_decompilations AS
SELECT DISTINCT ON (function_id) *
FROM reforge.decompilation_results
ORDER BY function_id, created_at DESC;

-- Experiment summary with metrics
CREATE OR REPLACE VIEW experiment_summary AS
SELECT 
    e.id,
    e.name,
    e.status,
    e.started_at,
    e.completed_at,
    COUNT(DISTINCT em.decompilation_id) as total_functions,
    AVG(em.codebleu_score) as avg_codebleu,
    SUM(CASE WHEN em.compilation_success THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) as compilation_rate,
    SUM(CASE WHEN em.exact_match THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) as exact_match_rate
FROM reforge.experiments e
LEFT JOIN reforge.evaluation_metrics em ON e.id = em.experiment_id
GROUP BY e.id;
