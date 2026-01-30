-- =============================================================================
-- Reforge - Provenance & Metadata Tracking Schema
-- Tracks all LLM interactions, decompilation artifacts, and experiment metrics
-- =============================================================================

SET search_path TO reforge, public;

-- =============================================================================
-- Binary Analysis Targets
-- =============================================================================
CREATE TABLE IF NOT EXISTS binaries (
    id UUID PRIMARY KEY DEFAULT public.uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    sha256_hash VARCHAR(64) UNIQUE NOT NULL,
    file_size BIGINT,
    architecture VARCHAR(50),  -- x86, x86_64, ARM, etc.
    compiler_info VARCHAR(255),
    optimization_level VARCHAR(10),  -- O0, O1, O2, O3, Os
    source_language VARCHAR(50),  -- C, C++, Rust, Go
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_binaries_hash ON binaries(sha256_hash);
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
