"""Test script for database-based Assemblage client.

This script tests the new database integration approach.
"""

import logging
from reforge.workers.assemblage_bridge.bridge.clients.assemblage_client import AssemblageClient, AssemblageConfig
from bridge.models import BuildRequest, BuildRecipe, BuildSystem, Compiler, OptimizationLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_connection():
    """Test database connection."""
    config = AssemblageConfig(
        db_host="localhost",  # Change to "assemblage-db" when running in Docker
        db_port=5433,  # Mapped port from docker-compose
        db_name="assemblage",
        db_user="assemblage",
        db_password="assemblage_pw",
    )
    
    client = AssemblageClient(config)
    
    logger.info("Testing connection...")
    if client.connect():
        logger.info("✓ Connected successfully")
    else:
        logger.error("✗ Connection failed")
        return False
    
    logger.info("Testing connection check...")
    if client.check_connection():
        logger.info("✓ Connection check passed")
    else:
        logger.error("✗ Connection check failed")
        return False
    
    client.disconnect()
    logger.info("✓ Disconnected successfully")
    return True


def test_submit_build():
    """Test build submission."""
    config = AssemblageConfig(
        db_host="localhost",
        db_port=5433,
        db_name="assemblage",
        db_user="assemblage",
        db_password="assemblage_pw",
    )
    
    client = AssemblageClient(config)
    
    if not client.connect():
        logger.error("Failed to connect")
        return False
    
    # Create test build request (cJSON example)
    request = BuildRequest(
        repo_url="https://github.com/DaveGamble/cJSON.git",
        commit_ref="master",
        recipe=BuildRecipe(
            build_system=BuildSystem.CMAKE,
            compiler=Compiler.CLANG,
            optimizations=[
                OptimizationLevel.NONE,
                OptimizationLevel.LOW,
                OptimizationLevel.MEDIUM,
                OptimizationLevel.HIGH,
            ],
        )
    )
    
    logger.info("Submitting build request...")
    try:
        repo_id, build_opt_id = client.submit_build(request, build_opt_id=1, priority="high")
        logger.info(f"✓ Build submitted: repo_id={repo_id}, build_opt_id={build_opt_id}")
        
        # Query status immediately
        logger.info("Querying status...")
        status = client.get_task_status(repo_id, build_opt_id)
        if status:
            logger.info(f"✓ Status retrieved:")
            logger.info(f"  - URL: {status.url}")
            logger.info(f"  - Build status: {status.build_status}")
            logger.info(f"  - Clone status: {status.clone_status}")
        else:
            logger.warning("✗ Could not retrieve status")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Build submission failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.disconnect()


def test_query_status():
    """Test status querying for existing build."""
    config = AssemblageConfig(
        db_host="localhost",
        db_port=5433,
        db_name="assemblage",
        db_user="assemblage",
        db_password="assemblage_pw",
    )
    
    client = AssemblageClient(config)
    
    if not client.connect():
        logger.error("Failed to connect")
        return False
    
    # Query a known repo_id (adjust as needed)
    repo_id = int(input("Enter repo_id to query (or press Enter to skip): ") or "0")
    
    if repo_id > 0:
        logger.info(f"Querying status for repo_id={repo_id}...")
        status = client.get_task_status(repo_id, build_opt_id=1)
        
        if status:
            logger.info(f"✓ Status found:")
            logger.info(f"  - URL: {status.url}")
            logger.info(f"  - Build status: {status.build_status}")
            logger.info(f"  - Clone status: {status.clone_status}")
            logger.info(f"  - Build msg: {status.build_msg}")
            logger.info(f"  - Build time: {status.build_time}")
            
            # Query binaries
            logger.info("Querying binaries...")
            binaries = client.get_binaries_for_task(repo_id)
            if binaries:
                logger.info(f"✓ Found {len(binaries)} binaries:")
                for bin in binaries:
                    logger.info(f"  - {bin['filename']} ({bin['optimization']}) - {bin['size']} bytes")
            else:
                logger.info("  No binaries found")
        else:
            logger.warning(f"✗ No status found for repo_id={repo_id}")
    
    client.disconnect()
    return True


if __name__ == "__main__":
    logger.info("=== Testing Database-based Assemblage Client ===\n")
    
    logger.info("1. Testing connection...")
    if test_connection():
        logger.info("✓ Connection test passed\n")
    else:
        logger.error("✗ Connection test failed\n")
        exit(1)
    
    logger.info("2. Testing build submission...")
    submit = input("Submit test build? (y/n): ").lower() == 'y'
    if submit:
        test_submit_build()
    else:
        logger.info("Skipped\n")
    
    logger.info("3. Testing status query...")
    query = input("Query status? (y/n): ").lower() == 'y'
    if query:
        test_query_status()
    else:
        logger.info("Skipped\n")
    
    logger.info("=== All tests complete ===")
