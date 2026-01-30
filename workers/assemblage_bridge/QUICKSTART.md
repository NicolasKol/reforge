# Quick Start Guide - Database-based Assemblage Bridge

## Prerequisites

1. Assemblage stack running with database accessible
2. Docker and Docker Compose installed
3. Network connectivity between Reforge and Assemblage stacks

## Setup Steps

### 1. Ensure Assemblage is Running

```bash
cd C:\Users\nico_\Documents\UNI\Thesis\Source\Assemblage
docker-compose -f docker-compose-s3.yml up -d
```

Verify services:
```bash
docker ps | grep assemblage
# Should see: assemblage-db, coordinator, builder_0, builder_1, minio, rabbitmq
```

### 2. Connect Networks

```bash
# Connect bridge to Assemblage network
docker network connect assemblage_default reforge-assemblage-bridge
```

### 3. Update Environment Variables

Create `.env` file in `reforge/docker/`:

```env
# Database connection
ASSEMBLAGE_DB_HOST=assemblage-db
ASSEMBLAGE_DB_PORT=5432
ASSEMBLAGE_DB_NAME=assemblage
ASSEMBLAGE_DB_USER=assemblage
ASSEMBLAGE_DB_PASSWORD=assemblage_pw

# S3/MinIO (use correct hostname)
ASSEMBLAGE_S3_ENDPOINT=http://minio:9000
ASSEMBLAGE_S3_ACCESS_KEY=minioadmin
ASSEMBLAGE_S3_SECRET_KEY=minioadmin
ASSEMBLAGE_S3_BUCKET=artifacts
```

### 4. Rebuild and Start Bridge

```bash
cd C:\Users\nico_\Documents\UNI\Thesis\Source\reforge\docker
docker-compose build assemblage-bridge
docker-compose up -d assemblage-bridge
```

### 5. Verify Health

```bash
# Check logs
docker logs reforge-assemblage-bridge

# Should see:
# - "Connected to Assemblage DB at assemblage-db:5432"
# - "Started Assemblage status polling"
# - "Assemblage Bridge started"

# Test health endpoint
curl http://localhost:8090/health
```

### 6. Test Build Submission

```bash
curl -X POST http://localhost:8090/build \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/DaveGamble/cJSON.git",
    "commit_ref": "master",
    "recipe": {
      "build_system": "cmake",
      "compiler": "clang",
      "optimizations": ["opt_NONE", "opt_HIGH"]
    }
  }'
```

Expected response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "recipe_hash": "abc123...",
  "message": "Build submitted to Assemblage database"
}
```

### 7. Monitor Progress

```bash
# Query job status
curl http://localhost:8090/build/{job_id}

# Watch database
docker exec assemblage-db psql -U assemblage -c \
  "SELECT repo_id, build_status, clone_status FROM b_status ORDER BY created_at DESC LIMIT 5"

# Watch coordinator logs
docker logs -f assemblage-coordinator

# Watch builder logs
docker logs -f builder_0
```

## Testing Locally (Without Docker)

### 1. Install Dependencies

```bash
cd C:\Users\nico_\Documents\UNI\Thesis\Source\reforge\workers\assemblage_bridge
pip install -r requirements.txt
```

### 2. Port Forward Database

```bash
# In Assemblage docker-compose-s3.yml, expose database port:
# ports:
#   - "5433:5432"

docker-compose -f docker-compose-s3.yml up -d
```

### 3. Run Test Script

```bash
python test_database_client.py
```

Follow prompts to:
1. Test connection
2. Submit test build (cJSON)
3. Query status

### 4. Run FastAPI Locally

```bash
# Set environment variables
$env:ASSEMBLAGE_DB_HOST="localhost"
$env:ASSEMBLAGE_DB_PORT="5433"
$env:ASSEMBLAGE_S3_ENDPOINT="http://localhost:9001"

# Start server
uvicorn main:app --reload --port 8090
```

Visit: http://localhost:8090/docs

## Verification Checklist

- [ ] Assemblage database accessible (port 5432 or 5433)
- [ ] Bridge connects to database successfully
- [ ] Build submission creates record in `b_status` table
- [ ] Coordinator picks up task and dispatches to builder
- [ ] Builder updates status in database
- [ ] Bridge polling detects status changes
- [ ] Artifacts uploaded to MinIO
- [ ] Bridge downloads artifacts when build completes

## Common Issues

### "Cannot connect to Assemblage database"

**Solution:**
```bash
# Check database is running
docker exec assemblage-db psql -U assemblage -c "SELECT 1"

# Check network
docker network inspect assemblage_default
```

### "Build submitted but coordinator not dispatching"

**Solution:**
```bash
# Check coordinator is running
docker logs assemblage-coordinator

# Verify INIT status in database
docker exec assemblage-db psql -U assemblage -c \
  "SELECT * FROM b_status WHERE build_status='INIT'"

# Restart coordinator if needed
docker restart assemblage-coordinator
```

### "Status not updating"

**Solution:**
```bash
# Check polling is running
docker logs reforge-assemblage-bridge | grep "Querying status"

# Verify database records
docker exec assemblage-db psql -U assemblage -c \
  "SELECT repo_id, build_status, clone_status, build_msg FROM b_status WHERE repo_id=<YOUR_REPO_ID>"
```

## Next Steps

1. **Submit curated builds:**
   - Create list of repositories
   - Submit via HTTP API
   - Monitor in n8n workflow

2. **Configure artifact download:**
   - Verify MinIO access
   - Test local storage path
   - Check artifact metadata

3. **Integrate with n8n:**
   - Create HTTP request node
   - Add polling logic
   - Trigger downstream analysis

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         Reforge Stack                        │
├─────────────────────────────────────────────────────────────┤
│  n8n  →  Assemblage Bridge (FastAPI on port 8090)          │
│                     ↓                                        │
│              SQLite (jobs.db) ← Job tracking                │
│                     ↓                                        │
│              PostgreSQL (Assemblage DB) ← Insert INIT       │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│                       Assemblage Stack                       │
├─────────────────────────────────────────────────────────────┤
│  Coordinator (polls DB) → RabbitMQ → Builders               │
│         ↓                              ↓                     │
│  Updates b_status                  Uploads to MinIO         │
│         ↓                              ↓                     │
│  Bridge polls ← Status            Bridge downloads          │
└─────────────────────────────────────────────────────────────┘
```

## Support

For issues or questions:
1. Check logs: `docker logs reforge-assemblage-bridge`
2. Verify database records with SQL queries
3. Review [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) for detailed architecture
4. Test connection with `test_database_client.py`
