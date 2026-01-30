# Interactive psql session
docker exec -it assemblage-db psql -U assemblage

# Or run a single query
docker exec -it assemblage-db psql -U assemblage -c "SELECT COUNT(*) FROM status WHERE build_status = 'init';"


-- List all tables
\dt

-- Describe a table structure
\d status
\d projects

-- See how many tasks are queued
SELECT COUNT(*) FROM status WHERE build_status = 'INIT';

-- See build status breakdown
SELECT build_status, COUNT(*) FROM status GROUP BY build_status;

-- See recent projects
SELECT * FROM projects LIMIT 10;

-- See tasks with their status
SELECT s.id, p.url, s.build_status, s.clone_status 
FROM status s 
JOIN projects p ON s.repo_id = p.id 
LIMIT 20;

-- Clear all init tasks (to stop the feeding)
DELETE FROM status WHERE build_status = 'init';

-- Exit psql
\q


# Count init tasks
docker exec assemblage-db psql -U assemblage -c "SELECT COUNT(*) FROM status WHERE build_status = 'init';"

# Delete all init tasks
docker exec assemblage-db psql -U assemblage -c "DELETE FROM status WHERE build_status = 'init';"

# See build status summary
docker exec assemblage-db psql -U assemblage -c "SELECT build_status, COUNT(*) FROM status GROUP BY build_status;"


# get db counts
docker exec assemblage-db psql -U assemblage -c "SELECT build_status, COUNT(*) FROM b_status GROUP BY build_status;"


# Delete the SQLite database file (will be recreated on next request)
docker exec reforge-assemblage-bridge rm -f /files/assemblage_bridge/jobs.db

# Then restart the bridge to reinitialize
docker restart reforge-assemblage-bridge

# docker rebuild & start
docker compose build assemblage-bridge  
docker compose up -d --force-recreate assemblage-bridge

# bridge network
docker network connect assemblage_default reforge-assemblage-bridge

### dispach build

{
  "repo_url": "https://github.com/DaveGamble/cJSON",
  "commit_ref": "master",
  "recipe": {
    "compiler": "gcc",
    "platform": "linux",
    "architecture": "x64",
    "optimizations": ["opt_NONE", "opt_HIGH", "opt_LOW", "opt_MEDIUM"],
    "build_system": "cmake",
    "save_assembly": false
  },
  "priority": "HIGH"
}