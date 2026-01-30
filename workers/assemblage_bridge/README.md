# Assemblage Bridge

HTTP API service bridging n8n orchestration to the Assemblage binary build system.

## Overview

The Assemblage Bridge provides a clean HTTP interface for:
- Submitting build requests to Assemblage via RabbitMQ
- Polling job status until completion
- Downloading built artifacts from MinIO to local storage
- Tracking job provenance with recipe hashing

**n8n only communicates with this bridge via HTTP** - no direct RabbitMQ or S3 access needed.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Reforge Docker Network                            │
│                                                                             │
│  ┌──────────┐    HTTP     ┌───────────────────┐                            │
│  │   n8n    │ ──────────→ │ Assemblage Bridge │                            │
│  │          │             │   (this service)  │                            │
│  └──────────┘             └─────────┬─────────┘                            │
│                                     │                                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │ Shared Network  │                 │
                    │                 ▼                 │
┌───────────────────┼───────────────────────────────────┼─────────────────────┐
│                   │    Assemblage Docker Network      │                     │
│                   │                                   │                     │
│  ┌────────────────▼───────────────┐   ┌──────────────▼────────────────┐   │
│  │         RabbitMQ               │   │          MinIO                │   │
│  │  (build task queue)            │   │   (artifact storage)          │   │
│  └────────────────────────────────┘   └───────────────────────────────┘   │
│                   │                                   ▲                     │
│                   ▼                                   │                     │
│  ┌────────────────────────────────┐                   │                     │
│  │        Assemblage              │                   │                     │
│  │   Coordinator + Builders       │───────────────────┘                     │
│  └────────────────────────────────┘    (uploads artifacts)                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API Endpoints

### Build Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/build` | Submit a new build request |
| `GET` | `/build/{job_id}` | Get job status and metadata |
| `GET` | `/build` | List all jobs (with filtering) |
| `POST` | `/build/{job_id}/retry` | Retry a failed build |
| `DELETE` | `/build/{job_id}` | Cancel a build |

### Artifacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/build/{job_id}/artifacts` | List job artifacts |
| `GET` | `/build/{job_id}/artifact/{filename}` | Download specific artifact |
| `POST` | `/build/{job_id}/download` | Manually trigger artifact download |

### Utility

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/recipe/hash` | Compute recipe hash |

## Environment Variables

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `ASSEMBLAGE_MQ_HOST` | RabbitMQ hostname | `assemblage-mq` |
| `ASSEMBLAGE_MQ_PORT` | RabbitMQ port | `5672` |
| `ASSEMBLAGE_S3_ENDPOINT` | MinIO endpoint URL | `http://assemblage-minio:9000` |
| `ASSEMBLAGE_S3_ACCESS_KEY` | MinIO access key | `minioadmin` |
| `ASSEMBLAGE_S3_SECRET_KEY` | MinIO secret key | `minioadmin` |
| `ASSEMBLAGE_S3_BUCKET` | Artifact bucket name | `artifacts` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `ASSEMBLAGE_MQ_USER` | RabbitMQ username | `guest` |
| `ASSEMBLAGE_MQ_PASSWORD` | RabbitMQ password | `guest` |
| `ASSEMBLAGE_MQ_VHOST` | RabbitMQ vhost | `/` |
| `ASSEMBLAGE_S3_REGION` | S3 region | `us-east-1` |
| `ASSEMBLAGE_BRIDGE_PORT` | Service port | `8090` |
| `ASSEMBLAGE_LOCAL_OUT_DIR` | Local artifact directory | `/files/binaries` |
| `ASSEMBLAGE_DB_PATH` | SQLite database path | `/files/assemblage_bridge/jobs.db` |
| `ASSEMBLAGE_DEFAULT_DATASET` | Default dataset name | `Reforge` |
| `ASSEMBLAGE_BRIDGE_API_KEY` | API key for auth | (none) |
| `ASSEMBLAGE_BRIDGE_REQUIRE_API_KEY` | Enable API key auth | `false` |

## Usage Examples

### Submit a Build

```bash
curl -X POST http://localhost:8090/build \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/example/myproject",
    "commit_ref": "v1.0.0",
    "recipe": {
      "compiler": "gcc",
      "platform": "linux",
      "architecture": "x64",
      "optimizations": ["opt_NONE", "opt_MEDIUM"],
      "build_system": "cmake"
    }
  }'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "QUEUED",
  "recipe_hash": "a1b2c3d4...",
  "message": "Build submitted to Assemblage"
}
```

### Poll Job Status

```bash
curl http://localhost:8090/build/550e8400-e29b-41d4-a716-446655440000
```

Response (in progress):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "BUILDING",
  "recipe_hash": "a1b2c3d4...",
  "created_at": "2025-01-26T10:00:00Z",
  "started_at": "2025-01-26T10:00:05Z",
  "progress_message": "Build [2]: Compiling..."
}
```

Response (complete):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "SUCCESS",
  "recipe_hash": "a1b2c3d4...",
  "created_at": "2025-01-26T10:00:00Z",
  "started_at": "2025-01-26T10:00:05Z",
  "finished_at": "2025-01-26T10:05:00Z",
  "artifact_count": 2,
  "artifacts": [
    {
      "filename": "myproject",
      "local_path": "/files/binaries/550e.../opt_NONE/myproject",
      "sha256": "abc123...",
      "size_bytes": 12345,
      "optimization": "opt_NONE"
    },
    {
      "filename": "myproject",
      "local_path": "/files/binaries/550e.../opt_MEDIUM/myproject",
      "sha256": "def456...",
      "size_bytes": 8765,
      "optimization": "opt_MEDIUM"
    }
  ]
}
```

### List Jobs

```bash
# All jobs
curl http://localhost:8090/build

# Filter by status
curl "http://localhost:8090/build?status=SUCCESS&limit=10"
```

## Recipe Hashing

Each build request includes a `recipe_hash` - a stable SHA256 hash of the canonical build configuration. This enables:

- **Deduplication**: Identify if the same build already exists
- **Provenance**: Track exact build parameters
- **Reproducibility**: Same recipe always produces same hash

Compute a hash without submitting a build:
```bash
curl -X POST http://localhost:8090/recipe/hash \
  -H "Content-Type: application/json" \
  -d '{
    "compiler": "gcc",
    "platform": "linux",
    "optimizations": ["opt_NONE"]
  }'
```

## Local Storage Layout

Artifacts are stored at:
```
/files/binaries/
└── <job_id>/
    ├── opt_NONE/
    │   └── binary_name
    ├── opt_LOW/
    │   └── binary_name
    ├── opt_MEDIUM/
    │   └── binary_name
    └── opt_HIGH/
        └── binary_name
```

Job metadata is persisted in SQLite at:
```
/files/assemblage_bridge/jobs.db
```

## n8n Workflow Integration

### Basic Workflow Pattern

1. **HTTP Request Node**: `POST /build` with repository and recipe
2. **Wait Node**: Loop with 30s delay
3. **HTTP Request Node**: `GET /build/{job_id}` 
4. **IF Node**: Check if `status` is terminal (SUCCESS/FAILED)
5. **Continue**: Pass `artifacts[].local_path` to next pipeline step

See [assemblage-build-request.json](../../n8n/workflows/assemblage-build-request.json) for a ready-to-import workflow.

## Running Locally (Development)

```bash
cd reforge/workers/assemblage_bridge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ASSEMBLAGE_MQ_HOST=localhost
export ASSEMBLAGE_S3_ENDPOINT=http://localhost:9000

# Run
python main.py
```

## Docker Deployment

The service is automatically built and started with the Reforge stack:

```bash
cd reforge/docker
docker compose up -d assemblage-bridge
```

View logs:
```bash
docker logs -f reforge-assemblage-bridge
```

## Network Requirements

For the bridge to work, both Docker stacks must share a network:

```bash
# Create shared network (if not exists)
docker network create assemblage-reforge-bridge

# In Assemblage docker-compose.yml, add:
networks:
  default:
    external:
      name: assemblage-reforge-bridge

# In Reforge docker-compose.yml, add same or join existing reforge-network
```

## Troubleshooting

### Cannot connect to RabbitMQ
- Verify Assemblage stack is running
- Check network connectivity: `docker exec reforge-assemblage-bridge ping assemblage-mq`
- Verify credentials in environment variables

### Artifacts not downloading
- Check MinIO is accessible: `curl http://assemblage-minio:9000/minio/health/live`
- Verify bucket exists and has artifacts
- Check `ASSEMBLAGE_S3_BUCKET` matches Assemblage configuration

### Jobs stuck in QUEUED
- Assemblage builders may not be running
- Check RabbitMQ queue: `docker exec assemblage-mq rabbitmqctl list_queues`
