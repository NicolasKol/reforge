# Implementation Summary - Database-based Assemblage Integration

## What Was Done

The Assemblage Bridge has been completely refactored from a RabbitMQ-based approach to a database-based approach that properly integrates with Assemblage's architecture.

## Files Changed

### Core Implementation

1. **`bridge/assemblage_client.py`** - Complete rewrite (323 → 384 lines)
   - Removed: RabbitMQ/pika dependencies, message classes, consumer threads
   - Added: PostgreSQL/psycopg2 client, database queries
   - Key methods:
     - `submit_build()`: Inserts to `projects` and `b_status` tables
     - `get_task_status()`: Queries current build/clone status
     - `get_binaries_for_task()`: Retrieves artifacts from database

2. **`main.py`** - Major refactor (649 → 646 lines)
   - Removed: RabbitMQ status handlers (`handle_clone_status`, `handle_build_status`, `handle_binary_notification`)
   - Added: `poll_status_updates()` background task (polls database every 5 seconds)
   - Updated: `lifespan()` to use database config and start polling
   - Updated: `submit_build()` endpoint to insert to database
   - Updated: Environment variable handling for database connection

3. **`requirements.txt`** - Dependency swap
   ```diff
   - pika>=1.3.2
   + psycopg2-binary>=2.9.9
   ```

4. **`docker/docker-compose.yml`** - Environment variables
   - Replaced RabbitMQ environment variables with database variables
   - Updated MinIO endpoint from `assemblage-minio` to `minio`

### Documentation

5. **`DATABASE_INTEGRATION.md`** - NEW
   - Comprehensive architecture documentation
   - Database schema reference
   - Usage examples
   - Migration guide
   - Troubleshooting

6. **`QUICKSTART.md`** - NEW
   - Step-by-step setup guide
   - Testing instructions
   - Common issues and solutions
   - Verification checklist

7. **`test_database_client.py`** - NEW
   - Connection testing
   - Build submission testing
   - Status query testing

## Key Architectural Changes

### Before (Broken)
```
Bridge → RabbitMQ (direct submission) → Builder
       ← RabbitMQ (status queues)
```
**Problems:**
- Bypassed coordinator's dispatch logic
- No database record (lost on restart)
- Conflicted with coordinator's status consumption

### After (Fixed)
```
Bridge → PostgreSQL (INSERT with status='INIT')
                ↓
         Coordinator (auto-dispatch)
                ↓
         RabbitMQ → Builder
                ↓
         PostgreSQL (status updates)
                ↑
         Bridge (polls every 5s)
```
**Benefits:**
- Works with Assemblage's architecture
- Database persistence
- Coordinator handles retry/timeout
- No conflicts

## Environment Variables

### New Variables Required

```env
# Database connection
ASSEMBLAGE_DB_HOST=assemblage-db
ASSEMBLAGE_DB_PORT=5432
ASSEMBLAGE_DB_NAME=assemblage
ASSEMBLAGE_DB_USER=assemblage
ASSEMBLAGE_DB_PASSWORD=assemblage_pw

# S3 (updated hostname)
ASSEMBLAGE_S3_ENDPOINT=http://minio:9000  # Changed from assemblage-minio
```

### Removed Variables

```env
# No longer needed
ASSEMBLAGE_MQ_HOST
ASSEMBLAGE_MQ_PORT
ASSEMBLAGE_MQ_USER
ASSEMBLAGE_MQ_PASSWORD
ASSEMBLAGE_MQ_VHOST
```

## Database Integration

### Tables Used

1. **`projects`** - Repository metadata
   ```sql
   INSERT INTO projects (url, language, build_system, created_at)
   VALUES (%s, %s, %s, %s)
   ON CONFLICT (url) DO UPDATE SET url = EXCLUDED.url
   RETURNING id
   ```

2. **`b_status`** - Build task queue
   ```sql
   INSERT INTO b_status (
       repo_id, build_opt_id, build_status, clone_status,
       priority, created_at, mod_timestamp
   ) VALUES (%s, %s, 'INIT', 'NOT_STARTED', %s, %s, %s)
   ```

3. **`binaries`** - Artifact records
   ```sql
   SELECT file_name, opt_level, save_path, sha256, file_size
   FROM binaries WHERE repo_id = %s
   ```

### Status Flow

1. Bridge inserts: `build_status='INIT'`, `clone_status='NOT_STARTED'`
2. Coordinator picks up: `build_status='PROCESSING'`
3. Builder clones: `clone_status='PROCESSING'` → `'SUCCESS'`
4. Builder builds: `build_status='PROCESSING'` → `'SUCCESS'` or `'FAILED'`
5. Bridge polls and detects completion

## Testing

### Unit Test
```bash
cd reforge/workers/assemblage_bridge
python test_database_client.py
```

### Integration Test
```bash
# Submit build
curl -X POST http://localhost:8090/build -d '{...}'

# Check status
curl http://localhost:8090/build/{job_id}

# Verify in database
docker exec assemblage-db psql -U assemblage -c \
  "SELECT * FROM b_status ORDER BY created_at DESC LIMIT 1"
```

## Deployment

### 1. Network Setup
```bash
docker network connect assemblage_default reforge-assemblage-bridge
```

### 2. Rebuild Container
```bash
cd reforge/docker
docker-compose build assemblage-bridge
docker-compose up -d assemblage-bridge
```

### 3. Verify
```bash
# Check logs
docker logs reforge-assemblage-bridge

# Should see:
# ✓ "Connected to Assemblage DB at assemblage-db:5432"
# ✓ "Started Assemblage status polling"
# ✓ "Assemblage Bridge started"

# Test health
curl http://localhost:8090/health
```

## Breaking Changes

If you have existing code using the old RabbitMQ-based client:

### Imports
```python
# Remove these imports
from bridge.assemblage_client import (
    BinaryNotificationMessage,
    BuildStatusMessage,
    CloneStatusMessage,
)
```

### Configuration
```python
# Old
config = AssemblageConfig(
    host="assemblage-mq",
    port=5672,
)

# New
config = AssemblageConfig(
    db_host="assemblage-db",
    db_port=5432,
    db_name="assemblage",
    db_user="assemblage",
    db_password="assemblage_pw",
)
```

### Submission
```python
# Old
task_id, opt_id = client.submit_build(request)

# New  
repo_id, build_opt_id = client.submit_build(request, build_opt_id=1)
```

### Status Monitoring
```python
# Old (consumer-based)
client.start_status_consumer(on_build_status=handler)

# New (polling-based)
status = client.get_task_status(repo_id, build_opt_id)
```

## Verification Steps

After deployment, verify:

- [ ] Bridge connects to database: `docker logs reforge-assemblage-bridge | grep "Connected to Assemblage DB"`
- [ ] Polling starts: `docker logs reforge-assemblage-bridge | grep "Started Assemblage status polling"`
- [ ] Build submission creates DB record: `docker exec assemblage-db psql -U assemblage -c "SELECT * FROM b_status WHERE build_status='INIT'"`
- [ ] Coordinator dispatches: `docker logs assemblage-coordinator | grep "Dispatching task"`
- [ ] Builder processes: `docker logs builder_0 | grep "Processing"`
- [ ] Status updates in DB: Query `b_status` table
- [ ] Artifacts in MinIO: Check http://localhost:9001
- [ ] Bridge downloads artifacts: Check `/files/binaries`

## Performance Considerations

### Polling Interval
Currently set to **5 seconds** in `poll_status_updates()`:
```python
await asyncio.sleep(5)
```

**Adjust based on:**
- Number of active jobs
- Database load
- Desired responsiveness

### Database Connection Pooling
Currently uses single connection. For production:
```python
# Consider using connection pool
from psycopg2 import pool
connection_pool = pool.ThreadedConnectionPool(1, 10, **db_params)
```

### Status Query Optimization
Current query includes JOIN with `projects` table:
```sql
SELECT b.*, p.url FROM b_status b JOIN projects p ON b.repo_id = p.id
```

For large datasets, consider:
- Adding index on `(repo_id, build_opt_id)`
- Caching project URL lookups
- Batch querying multiple jobs

## Next Steps

### Immediate
1. ✅ Test connection to Assemblage database
2. ⏳ Submit test build (cJSON)
3. ⏳ Verify coordinator dispatches
4. ⏳ Confirm status polling works
5. ⏳ Test artifact download

### Short-term
1. Implement bulk submission endpoint
2. Add webhook notifications
3. Optimize polling frequency
4. Add metrics/monitoring

### Long-term
1. Connection pooling for scalability
2. Redis cache for status lookups
3. Webhook support for real-time updates
4. Admin UI for job management

## Resources

- **Architecture docs:** [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md)
- **Setup guide:** [QUICKSTART.md](QUICKSTART.md)
- **Test script:** [test_database_client.py](test_database_client.py)
- **Assemblage repo:** [Assemblage backend](../../Assemblage/backend/)

## Summary

The refactoring is **complete and ready for testing**. The new database-based approach:

✅ Aligns with Assemblage's architecture  
✅ Uses coordinator's dispatch logic  
✅ Persists across restarts  
✅ Avoids RabbitMQ conflicts  
✅ Simplifies status monitoring  
✅ Maintains FastAPI interface  

**No changes needed to n8n workflows** - the HTTP API remains the same, only the backend integration method changed.
