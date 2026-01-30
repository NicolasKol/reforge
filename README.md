# Reforge

**LLM-Assisted Reverse Engineering Orchestration Framework**

Reforge is a self-hostable orchestration platform for automated binary decompilation using Large Language Models. It provides reproducible workflows for lifting compiled binaries back to human-readable source code with provenance tracking and iterative validation.

## Key Features

- **Distributed Control Plane**: Docker-based deployment with n8n orchestration, Redis queues, and PostgreSQL provenance tracking
- **Modular Workflows**: Plug-and-play LLM selection with versioned prompt templates
- **Iterative Repair**: Compilation feedback loops with ASAN validation for functionally correct output
- **Experiment Tracking**: Full provenance of every LLM interaction, metric calculation, and artifact storage

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) Local Ghidra installation for binary analysis

### Setup

1. **Clone and configure environment**
   ```bash
   cd reforge/docker
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Generate encryption key**
   ```bash
   # Linux/Mac
   openssl rand -hex 32
   # Add output to N8N_ENCRYPTION_KEY in .env
   ```

3. **Start the stack**
   ```bash
   docker-compose up -d
   ```

4. **Access n8n**
   
   Open http://localhost:5678 in your browser


## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        n8n Orchestration                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  Binary  │→ │    IR    │→ │   LLM    │→ │   Validation     │ │
│  │  Lifting │  │ Context  │  │ Decompile│  │   & Repair       │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │                           │                    │
         ▼                           ▼                    ▼
┌─────────────┐             ┌──────────────┐      ┌─────────────┐
│   Ghidra    │             │   OpenAI /   │      │   GCC /     │
│   Worker    │             │   Anthropic  │      │   Clang     │
│             │             │   / Ollama   │      │   + ASAN    │
└─────────────┘             └──────────────┘      └─────────────┘
         │                           │                    │
         └───────────────────────────┴────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
            ┌─────────────┐           ┌─────────────┐
            │ PostgreSQL  │           │    Redis    │
            │ Provenance  │           │   Queues    │
            └─────────────┘           └─────────────┘
```

## Workflows

### Core Pipelines (planned)

| Workflow | Description |
|----------|-------------|
| `01-binary-intake.json` | Import binary, extract functions, compute hashes |
| `02-decompile-llm.json` | LLM-based decompilation with model selection |
| `03-validation-loop.json` | Compile + ASAN feedback for iterative repair |
| `04-batch-experiment.json` | Run experiments across binary corpus |

### Importing Workflows

1. Open n8n at http://localhost:5678
2. Go to **Workflows** → **Import from File**
3. Select workflow JSON from `n8n/workflows/`

## Database Schema

Key tables in the `reforge` schema:

- **`binaries`** - Analyzed binary metadata
- **`functions`** - Extracted functions with decompiled code
- **`llm_interactions`** - Full provenance of every LLM call
- **`decompilation_results`** - Generated code with validation status
- **`experiments`** - Experiment runs with aggregated metrics


## Documentation

- [Orchestration Design](../docs/Orchestration_reverse_engineering_LLM.md) - Architecture rationale
- [n8n Docker Cheatsheet](../docs/cheatsheets/n8n-docker.md) - Quick reference

## License

[TBD]

## Acknowledgments

Part of thesis research on LLM-assisted binary analysis.
