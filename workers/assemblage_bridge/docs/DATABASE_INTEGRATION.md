# Assemblage Bridge - Database Integration

## Overview

The Assemblage Bridge has been refactored to use **database insertion** instead of **direct RabbitMQ submission**. This aligns with Assemblage's architecture where the coordinator continuously polls the database for tasks with `build_status='INIT'` and auto-dispatches them.

## Architecture Changes

### Before (RabbitMQ-based)
```
n8n → FastAPI Bridge → RabbitMQ (build_opt_X queues) → Builder workers
                     ↓
               RabbitMQ (status queues) ← Builder workers
```

**Problems:**
- Direct queue submission bypassed coordinator's retry/timeout logic
- Status queues conflicted with coordinator's consumption
- No database record meant no recovery after restart

### After (Database-based)
```
n8n → FastAPI Bridge → PostgreSQL (projects + b_status tables)
                                        ↓
                              Coordinator (polls INIT status)
                                        ↓
                              RabbitMQ → Builder workers
                                        ↓
                              PostgreSQL (status updates)
                                        ↑
                     FastAPI Bridge (polls for status)
```

**Benefits:**
- Coordinator handles all dispatch logic (retry, timeout, priority)
- Database is source of truth for task state
- Survives restarts (persistent queue)
- No conflicts with Assemblage internals

## Key Changes

### 1. `assemblage_client.py`
- **Removed:** `pika` (RabbitMQ client), message classes, consumer threads
- **Added:** `psycopg2` (PostgreSQL client), database queries
- **Methods:**
  - `submit_build()`: Inserts into `projects` and `b_status` tables with status='INIT'
  - `get_task_status()`: Queries current build/clone status from database
  - `get_binaries_for_task()`: Retrieves binary artifacts from database

### 2. `main.py`
- **Removed:** RabbitMQ status consumers, message handlers
- **Added:** Background polling task (`poll_status_updates()`)
- **Changes:**
  - Lifespan: Connects to database, starts polling loop
  - `submit_build`: Inserts to database, tracks `(repo_id, build_opt_id)` tuple
  - Polling: Checks database every 5 seconds for status updates

### 3. Environment Variables

#### Old (RabbitMQ):
```env
ASSEMBLAGE_MQ_HOST=assemblage-mq
ASSEMBLAGE_MQ_PORT=5672
ASSEMBLAGE_MQ_USER=guest
ASSEMBLAGE_MQ_PASSWORD=guest
```

#### New (Database):
```env
ASSEMBLAGE_DB_HOST=assemblage-db
ASSEMBLAGE_DB_PORT=5432
ASSEMBLAGE_DB_NAME=assemblage
ASSEMBLAGE_DB_USER=assemblage
ASSEMBLAGE_DB_PASSWORD=assemblage_pw
```

### 4. Dependencies

#### `requirements.txt`
```diff
- pika>=1.3.2
+ psycopg2-binary>=2.9.9
```

## Database Schema

### `projects` Table
```sql
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    language TEXT,
    build_system TEXT,
    created_at TIMESTAMP
);
```

### `b_status` Table
```sql
CREATE TABLE b_status (
    id SERIAL PRIMARY KEY,
    repo_id INTEGER REFERENCES projects(id),
    build_opt_id INTEGER,
    build_status TEXT,  -- 'INIT', 'PROCESSING', 'SUCCESS', 'FAILED', 'TIMEOUT'
    clone_status TEXT,  -- 'NOT_STARTED', 'PROCESSING', 'SUCCESS', 'FAILED', 'TIMEOUT'
    priority TEXT,      -- 'low', 'medium', 'high'
    build_msg TEXT,
    clone_msg TEXT,
    build_time INTEGER,
    commit_hexsha TEXT,
    created_at TIMESTAMP,
    mod_timestamp BIGINT
);
```

### `binaries` Table
```sql
CREATE TABLE binaries (
    id SERIAL PRIMARY KEY,
    repo_id INTEGER REFERENCES projects(id),
    file_name TEXT,
    opt_level TEXT,
    save_path TEXT,
    sha256 TEXT,
    file_size INTEGER
);
```

## Usage

### Testing Connection

```bash
cd C:\Users\nico_\Documents\UNI\Thesis\Source\reforge\workers\assemblage_bridge
python test_database_client.py
```

### Submitting a Build

```python
from bridge.assemblage_client import AssemblageClient, AssemblageConfig
from bridge.models import BuildRequest, BuildRecipe, BuildSystem, Compiler, OptimizationLevel

config = AssemblageConfig(
    db_host="assemblage-db",
    db_port=5432,
    db_name="assemblage",
    db_user="assemblage",
    db_password="assemblage_pw",
)

client = AssemblageClient(config)
client.connect()

request = BuildRequest(
    repo_url="https://github.com/DaveGamble/cJSON.git",
    commit_ref="master",
    recipe=BuildRecipe(
        build_system=BuildSystem.CMAKE,
        compiler=Compiler.CLANG,
        optimizations=[OptimizationLevel.NONE, OptimizationLevel.HIGH],
    )
)

repo_id, build_opt_id = client.submit_build(request, build_opt_id=1, priority="high")
print(f"Submitted: repo_id={repo_id}, build_opt_id={build_opt_id}")
```

### Polling Status

```python
status = client.get_task_status(repo_id=123, build_opt_id=1)
if status:
    print(f"Build: {status.build_status}, Clone: {status.clone_status}")
    print(f"Message: {status.build_msg}")

# Get binaries
binaries = client.get_binaries_for_task(repo_id=123)
for bin in binaries:
    print(f"{bin['filename']} ({bin['optimization']}) - {bin['size']} bytes")
```

## Deployment

### Docker Compose

```yaml
assemblage-bridge:
  environment:
    # Database connection
    - ASSEMBLAGE_DB_HOST=assemblage-db
    - ASSEMBLAGE_DB_PORT=5432
    - ASSEMBLAGE_DB_NAME=assemblage
    - ASSEMBLAGE_DB_USER=assemblage
    - ASSEMBLAGE_DB_PASSWORD=assemblage_pw
    # S3/MinIO
    - ASSEMBLAGE_S3_ENDPOINT=http://minio:9000
    - ASSEMBLAGE_S3_ACCESS_KEY=minioadmin
    - ASSEMBLAGE_S3_SECRET_KEY=minioadmin
  networks:
    - assemblage_default  # Must connect to Assemblage network
```

### Network Connection

The bridge must be on the same network as the Assemblage stack:

```bash
# If not already configured in docker-compose
docker network connect assemblage_default reforge-assemblage-bridge
```

## Workflow

1. **Submit build via HTTP API:**
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

2. **Bridge inserts to database:**
   - Creates record in `projects` table (or reuses existing)
   - Inserts to `b_status` with `build_status='INIT'`, `clone_status='NOT_STARTED'`

3. **Coordinator auto-dispatches:**
   - Polls database every few seconds
   - Finds tasks with `build_status='INIT'`
   - Publishes to RabbitMQ `build_opt_X` queue

4. **Builder processes:**
   - Clones repository (updates `clone_status`)
   - Builds at each optimization level (updates `build_status`)
   - Uploads binaries to MinIO S3
   - Records in `binaries` table

5. **Bridge polls for status:**
   - Every 5 seconds checks `b_status` table
   - Updates internal job state
   - When `build_status='SUCCESS'`, triggers artifact download

6. **Query job status:**
   ```bash
   curl http://localhost:8090/build/{job_id}
   ```

## Troubleshooting

### Connection Fails
```bash
# Check if database is accessible
docker exec assemblage-db psql -U assemblage -c "SELECT 1"

# Check network
docker network inspect assemblage_default | grep reforge-assemblage-bridge
```

### Build Not Dispatching
```bash
# Check if coordinator is running
docker logs assemblage-coordinator

# Verify database record
docker exec assemblage-db psql -U assemblage -c \
  "SELECT * FROM b_status WHERE build_status='INIT'"
```

### No Status Updates
```bash
# Check bridge logs
docker logs reforge-assemblage-bridge

# Verify polling is working (should see queries every 5 seconds)
```

## Migration from Old Version

If you have existing code using the old RabbitMQ-based approach:

1. **Update imports:**
   ```python
   # Remove
   from bridge.assemblage_client import (
       BinaryNotificationMessage,
       BuildStatusMessage, 
       CloneStatusMessage,
   )
   ```

2. **Update config:**
   ```python
   # Old
   config = AssemblageConfig(
       host="assemblage-mq",
       port=5672,
       username="guest",
       password="guest",
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

3. **Update submission:**
   ```python
   # Old
   task_id, opt_id = client.submit_build(request)
   
   # New
   repo_id, build_opt_id = client.submit_build(request, build_opt_id=1)
   ```

4. **Replace status consumers with polling:**
   ```python
   # Old
   client.start_status_consumer(
       on_clone_status=handler,
       on_build_status=handler,
   )
   
   # New
   while True:
       status = client.get_task_status(repo_id, build_opt_id)
       if status:
           print(f"Status: {status.build_status}")
       await asyncio.sleep(5)
   ```

## Benefits of Database Integration

1. **Reliability:** Database persists across restarts, no lost tasks
2. **Simplicity:** No need to manage RabbitMQ consumers
3. **Compatibility:** Works with Assemblage's existing architecture
4. **Observability:** Easy to query task state with SQL
5. **Scalability:** Coordinator handles dispatch logic, load balancing

## Next Steps

- Test with curated repository list
- Implement bulk submission endpoint
- Add webhook notifications for completion
- Optimize polling frequency based on active jobs
