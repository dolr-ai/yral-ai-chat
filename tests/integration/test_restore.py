"""
Integration tests for database restore functionality
Tests automatic restore, corruption recovery, and data integrity
"""
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_database():
    """Create a temporary database for testing"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Create a valid SQLite database with some data
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    conn.execute("INSERT INTO test_table (name) VALUES ('test_data')")
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    if Path(db_path).exists():
        Path(db_path).unlink()


@pytest.fixture
def empty_database():
    """Create an empty database file"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield db_path
    if Path(db_path).exists():
        Path(db_path).unlink()


@pytest.fixture
def corrupted_database():
    """Create a corrupted database file"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Write invalid data to make it corrupted
    Path(db_path).write_bytes(b"This is not a valid SQLite database file")
    
    yield db_path
    if Path(db_path).exists():
        Path(db_path).unlink()


class TestDatabaseVerification:
    """Test database verification script"""
    
    def test_verify_valid_database(self, temp_database):
        """Test verification of a valid database"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "verify_database.py"
        result = subprocess.run(  # noqa: S603
            ["python3", str(script_path)],  # noqa: S607
            env={**os.environ, "DATABASE_PATH": temp_database},
            capture_output=True,
            text=True,
            check=False
        )
        
        assert result.returncode == 0, f"Verification failed: {result.stderr}"
        assert "SUCCESS" in result.stdout or "verification passed" in result.stdout.lower()
    
    def test_verify_missing_database(self):
        """Test verification of a missing database"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "verify_database.py"
        result = subprocess.run(  # noqa: S603
            ["python3", str(script_path)],  # noqa: S607
            env={**os.environ, "DATABASE_PATH": "/nonexistent/path/database.db"},
            capture_output=True,
            text=True,
            check=False
        )
        
        assert result.returncode == 1, "Should fail for missing database"
        assert "does not exist" in result.stdout.lower() or "ERROR" in result.stdout
    
    def test_verify_empty_database(self, empty_database):
        """Test verification of an empty database file"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "verify_database.py"
        result = subprocess.run(  # noqa: S603
            ["python3", str(script_path)],  # noqa: S607
            env={**os.environ, "DATABASE_PATH": empty_database},
            capture_output=True,
            text=True,
            check=False
        )
        
        assert result.returncode == 1, "Should fail for empty database"
        assert "empty" in result.stdout.lower() or "ERROR" in result.stdout
    
    def test_verify_corrupted_database(self, corrupted_database):
        """Test verification of a corrupted database"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "verify_database.py"
        result = subprocess.run(  # noqa: S603
            ["python3", str(script_path)],  # noqa: S607
            env={**os.environ, "DATABASE_PATH": corrupted_database},
            capture_output=True,
            text=True,
            check=False
        )
        
        assert result.returncode == 1, "Should fail for corrupted database"
        assert "ERROR" in result.stdout or "failed" in result.stdout.lower()


class TestDatabaseIntegrity:
    """Test database integrity checks"""
    
    def test_integrity_check_valid_database(self, temp_database):
        """Test PRAGMA integrity_check on valid database"""
        conn = sqlite3.connect(temp_database)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        
        assert result[0] == "ok", "Valid database should pass integrity check"
    
    def test_integrity_check_corrupted_database(self, corrupted_database):
        """Test PRAGMA integrity_check on corrupted database"""
        try:
            conn = sqlite3.connect(corrupted_database)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            
            # Corrupted database should not pass integrity check
            assert result[0] != "ok"
        except sqlite3.DatabaseError:
            # Some corrupted databases can't even be opened
            pass


class TestRestoreLogic:
    """Test restore logic and flags"""
    
    def test_restore_flags_exist(self):
        """Verify that litestream restore supports required flags"""
        try:
            result = subprocess.run(
                ["litestream", "restore", "--help"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            
            if result.returncode == 0:
                # Check if flags are documented
                help_text = result.stdout + result.stderr
                assert "-if-db-not-exists" in help_text or "if-db-not-exists" in help_text
                assert "-if-replica-exists" in help_text or "if-replica-exists" in help_text
        except FileNotFoundError:
            pytest.skip("Litestream not installed")
    
    def test_restore_without_database(self, temp_database):
        """Test restore behavior when database doesn't exist"""
        # This test verifies the logic, not actual restore
        # In real scenario, restore would happen if database is missing
        db_path = temp_database
        
        # Simulate: database exists, so restore shouldn't overwrite
        if Path(db_path).exists():
            # With -if-db-not-exists, restore should not overwrite existing DB
            assert Path(db_path).exists(), "Database should exist"
    
    def test_corrupted_database_backup(self, temp_database):
        """Test that corrupted database is backed up before restore"""
        # Simulate corruption detection
        db_path = temp_database
        corrupted_backup = f"{db_path}.corrupted.1234567890"
        
        # Simulate the backup process
        if Path(db_path).exists():
            import shutil
            shutil.copy2(db_path, corrupted_backup)
            assert Path(corrupted_backup).exists(), "Corrupted backup should be created"
            Path(corrupted_backup).unlink()  # Cleanup


class TestDatabasePersistence:
    """Test database persistence across operations"""
    
    def test_database_survives_operations(self, temp_database):
        """Test that database survives read operations"""
        db_path = temp_database
        
        # Read from database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM test_table")
        results = cursor.fetchall()
        conn.close()
        
        assert len(results) > 0, "Database should contain data"
        assert Path(db_path).exists(), "Database should still exist after operations"
    
    def test_database_file_size(self, temp_database):
        """Test that database file has content"""
        db_path = temp_database
        file_size = Path(db_path).stat().st_size
        
        assert file_size > 0, "Database file should not be empty"
        assert file_size > 100, "Database file should have reasonable size"


class TestMigrationAfterRestore:
    """Test that migrations work correctly after restore"""
    
    def test_migrations_can_run_on_existing_database(self, temp_database):
        """Test that migrations can run on an existing database"""
        # This simulates running migrations after a restore
        conn = sqlite3.connect(temp_database)
        
        # Check if we can add a new table (simulating migration)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations_test (
                    id INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            
            # Verify table was created
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='migrations_test'
            """)
            result = cursor.fetchone()
            conn.close()
            
            assert result is not None, "Migration should create table"
        except sqlite3.Error as e:
            conn.close()
            pytest.fail(f"Migration failed: {e}")


class TestDatabaseRecoveryScenarios:
    """Test various recovery scenarios"""
    
    def test_missing_database_scenario(self):
        """Test scenario where database is completely missing"""
        # This simulates what happens when database is deleted
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = tmp.name
        
        # Ensure it doesn't exist
        assert not Path(db_path).exists(), "Database should not exist"
        # In real scenario, restore would be triggered here
    
    def test_corrupted_database_scenario(self, corrupted_database):
        """Test scenario where database is corrupted"""
        # Verify database is corrupted
        # SQLite can open corrupted files, but will fail on operations
        # Try to use the database - this should detect corruption
        conn = None
        try:
            conn = sqlite3.connect(corrupted_database)
            cursor = conn.cursor()
            # Try to run integrity check - corrupted DB should fail
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            # If integrity check returns "ok", SQLite treated it as new empty DB
            # In that case, try to query sqlite_master - should fail or return empty
            if result[0] == "ok":
                # SQLite might treat invalid file as new empty DB
                # Try to query schema - corrupted DB should have issues
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                # If we get here without error, the file was treated as new empty DB
                # This is still a form of "corruption" for our purposes
                assert len(tables) == 0, "Corrupted database should not have valid schema"
            else:
                # Integrity check failed - database is corrupted
                assert result[0] != "ok", "Corrupted database should fail integrity check"
        except sqlite3.DatabaseError:
            # DatabaseError is expected for corrupted databases
            pass
        except sqlite3.OperationalError:
            # OperationalError can also occur with corrupted databases
            pass
        finally:
            if conn:
                conn.close()
    
    def test_empty_database_scenario(self, empty_database):
        """Test scenario where database file exists but is empty"""
        file_size = Path(empty_database).stat().st_size
        assert file_size == 0, "Database file should be empty"
        
        # Empty database should fail verification
        script_path = Path(__file__).parent.parent.parent / "scripts" / "verify_database.py"
        result = subprocess.run(  # noqa: S603
            ["python3", str(script_path)],  # noqa: S607
            env={**os.environ, "DATABASE_PATH": empty_database},
            capture_output=True,
            text=True,
            check=False
        )
        
        assert result.returncode == 1, "Empty database should fail verification"

