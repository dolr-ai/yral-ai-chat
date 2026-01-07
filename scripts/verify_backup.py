#!/usr/bin/env python3
"""
Backup verification script for Litestream
Checks if backups exist in S3, verifies backup age, and tests Litestream connectivity
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Expected tables that should exist after migrations
EXPECTED_TABLES = ["ai_influencers", "conversations", "messages"]


def generate_litestream_config(database_path: str) -> str:
    """Generate a temporary Litestream config file"""
    config_content = f"""# Litestream Configuration (generated dynamically)
dbs:
  - path: {database_path}
    replicas:
      - type: s3
        bucket: {os.getenv('LITESTREAM_BUCKET')}
        path: yral-ai-chat/{Path(database_path).name}
        endpoint: {os.getenv('LITESTREAM_ENDPOINT', '')}
        region: {os.getenv('LITESTREAM_REGION', 'us-east-1')}
        access-key-id: {os.getenv('LITESTREAM_ACCESS_KEY_ID')}
        secret-access-key: {os.getenv('LITESTREAM_SECRET_ACCESS_KEY')}
        sync-interval: 10s
        retention: 24h
        retention-check-interval: 1h
        snapshot-interval: 1h
"""
    fd, config_path = tempfile.mkstemp(suffix=".yml", text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(config_content)
        return config_path
    except Exception:
        os.close(fd)
        raise


def check_litestream_installed() -> bool:
    """Check if litestream binary is available"""
    try:
        result = subprocess.run(
            ["litestream", "version"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_s3_connectivity(config_path: str) -> tuple[bool, str]:
    """
    Check if Litestream can connect to S3
    Returns (success, message)
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["litestream", "databases", "-config", config_path],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
        
        if result.returncode == 0:
            return True, "S3 connectivity check passed"
        error_msg = result.stderr.strip() or result.stdout.strip()
        return False, f"S3 connectivity check failed: {error_msg}"
    except subprocess.TimeoutExpired:
        return False, "S3 connectivity check timed out"
    except Exception as e:
        return False, f"S3 connectivity check error: {e!s}"


def check_backup_exists(config_path: str, database_path: str) -> tuple[bool, str]:  # noqa: PLR0911
    """
    Check if a backup exists for the database
    Returns (exists, message)
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["litestream", "snapshots", "-config", config_path, database_path],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if output and "no snapshots" not in output.lower():
                lines = [line for line in output.split("\n") if line.strip() and not line.startswith("replica")]
                snapshot_count = len([line for line in lines if line.strip()])
                if snapshot_count > 0:
                    return True, f"Backup exists ({snapshot_count} snapshot(s) found)"
                return False, "No snapshots found in backup"
            return False, "No backup found (no snapshots available)"
        error_msg = result.stderr.strip() or result.stdout.strip()
        if "no snapshots" in error_msg.lower() or "not found" in error_msg.lower():
            return False, "No backup found"
        return False, f"Error checking backup: {error_msg}"
    except subprocess.TimeoutExpired:
        return False, "Backup check timed out"
    except Exception as e:
        return False, f"Backup check error: {e!s}"


def get_latest_backup_age(config_path: str, database_path: str) -> tuple[bool, str, datetime | None]:
    """
    Get the age of the latest backup
    Returns (success, message, latest_backup_time)
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["litestream", "snapshots", "-config", config_path, database_path],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            # Format is typically: replica  path  created
            lines = [line for line in output.split("\n") if line.strip() and not line.startswith("replica")]
            
            if not lines:
                return False, "No snapshots found", None
            
            # Litestream snapshot output format may vary, so we'll look for ISO timestamps
            latest_time = None
            for line in lines:
                parts = line.split()
                for part in parts:
                    try:
                        if "T" in part or "-" in part:
                            # Remove timezone info if present
                            clean_part = part.split("+")[0].split("Z")[0]
                            dt = datetime.fromisoformat(clean_part)
                            if latest_time is None or dt > latest_time:
                                latest_time = dt
                    except (ValueError, AttributeError):
                        continue
            
            if latest_time:
                age = datetime.now() - latest_time
                age_hours = age.total_seconds() / 3600
                return True, f"Latest backup is {age_hours:.1f} hours old", latest_time
            return True, "Backup exists but timestamp parsing failed", None
        return False, "Failed to get backup age", None
    except Exception as e:
        return False, f"Error getting backup age: {e!s}", None


def verify_backup_requirements() -> bool:
    """Verify all required environment variables are set"""
    required_vars = [
        "LITESTREAM_BUCKET",
        "LITESTREAM_ACCESS_KEY_ID",
        "LITESTREAM_SECRET_ACCESS_KEY"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")  # noqa: T201
        return False
    return True


def main():  # noqa: PLR0912, PLR0915
    """Main entry point"""
    print("=" * 60)  # noqa: T201
    print("Litestream Backup Verification")  # noqa: T201
    print("=" * 60)  # noqa: T201
    print()  # noqa: T201
    
    print("1. Checking if Litestream is installed...")  # noqa: T201
    if not check_litestream_installed():
        print("   ERROR: Litestream binary not found")  # noqa: T201
        print("   Please ensure Litestream is installed and in PATH")  # noqa: T201
        sys.exit(1)
    print("   ✓ Litestream is installed")  # noqa: T201
    print()  # noqa: T201
    
    print("2. Checking environment variables...")  # noqa: T201
    if not verify_backup_requirements():
        sys.exit(1)
    print("   ✓ All required environment variables are set")  # noqa: T201
    print()  # noqa: T201
    
    database_path = os.getenv("DATABASE_PATH", "/app/data/yral_chat.db")
    
    if not Path(database_path).is_absolute():
        project_root = Path("/app") if Path("/app/migrations").exists() else Path(__file__).parent.parent
        database_path = str((project_root / database_path).resolve())
    
    print(f"3. Database path: {database_path}")  # noqa: T201
    print()  # noqa: T201
    
    print("4. Generating Litestream configuration...")  # noqa: T201
    try:
        config_path = generate_litestream_config(database_path)
        print(f"   ✓ Config generated: {config_path}")  # noqa: T201
    except Exception as e:
        print(f"   ERROR: Failed to generate config: {e}")  # noqa: T201
        sys.exit(1)
    print()  # noqa: T201
    
    print("5. Checking S3 connectivity...")  # noqa: T201
    connected, message = check_s3_connectivity(config_path)
    if connected:
        print(f"   ✓ {message}")  # noqa: T201
    else:
        print(f"   ✗ {message}")  # noqa: T201
        print("   WARNING: Cannot verify backups without S3 connectivity")  # noqa: T201
    print()  # noqa: T201
    
    print("6. Checking if backup exists...")  # noqa: T201
    exists, message = check_backup_exists(config_path, database_path)
    if exists:
        print(f"   ✓ {message}")  # noqa: T201
    else:
        print(f"   ⚠ {message}")  # noqa: T201
        print("   NOTE: This is normal for a new database that hasn't been backed up yet")  # noqa: T201
    print()  # noqa: T201
    
    if exists:
        print("7. Checking backup age...")  # noqa: T201
        success, message, backup_time = get_latest_backup_age(config_path, database_path)
        if success:
            print(f"   ✓ {message}")  # noqa: T201
            if backup_time:
                retention_hours = 24
                age_hours = (datetime.now() - backup_time).total_seconds() / 3600
                if age_hours > retention_hours:
                    print(f"   ⚠ WARNING: Backup age ({age_hours:.1f}h) exceeds retention period ({retention_hours}h)")  # noqa: T201
                else:
                    print("   ✓ Backup is within retention period")  # noqa: T201
        else:
            print(f"   ⚠ {message}")  # noqa: T201
        print()  # noqa: T201
    
    try:
        Path(config_path).unlink()
    except Exception:
        pass
    
    print("=" * 60)  # noqa: T201
    if connected and exists:
        print("✓ Backup verification completed successfully")  # noqa: T201
        print("  The database backup exists and is accessible")  # noqa: T201
        sys.exit(0)
    elif connected and not exists:
        print("⚠ Backup verification completed with warnings")  # noqa: T201
        print("  S3 connectivity is working, but no backup found yet")  # noqa: T201
        print("  This is normal for a new database")  # noqa: T201
        sys.exit(0)
    else:
        print("✗ Backup verification completed with errors")  # noqa: T201
        print("  Please check S3 connectivity and configuration")  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    main()

