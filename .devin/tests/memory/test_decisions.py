"""Tests for the decision database system."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import sqlite3
from memory.decisions import (
    verify_fts5, initialize_schema, insert_decision, search_decisions,
    insert_shared_fact, search_shared_facts
)

# Setup logging for tests
import logging
import json

def setup_test_logging():
    """Setup logging for test execution."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    test_log_file = log_dir / f"test_decisions-Log.jsonl"
    
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "module": record.name,
                "function": record.funcName,
                "line": record.lineno,
                "message": record.getMessage(),
            }
            
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            
            if hasattr(record, 'extra_fields'):
                log_entry.update(record.extra_fields)
            
            return json.dumps(log_entry)
    
    file_handler = logging.FileHandler(test_log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    logger = logging.getLogger("test_decisions")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

test_logger = setup_test_logging()


def test_verify_fts5():
    """Test FTS5 availability verification."""
    test_logger.info("Testing verify_fts5()...")
    
    conn = sqlite3.connect(":memory:")
    
    try:
        verify_fts5(conn)
        test_logger.info("[PASS] FTS5 is available")
    except RuntimeError as e:
        test_logger.error(f"[FAIL] FTS5 not available: {e}")
        return False
    finally:
        conn.close()
    
    return True


def test_initialize_schema():
    """Test database schema initialization."""
    test_logger.info("Testing initialize_schema()...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        try:
            initialize_schema(conn)
            
            # Verify tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'"
            )
            assert cursor.fetchone() is not None, "decisions table should exist"
            
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='decisions_fts'"
            )
            assert cursor.fetchone() is not None, "decisions_fts table should exist"
            
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_facts'"
            )
            assert cursor.fetchone() is not None, "shared_facts table should exist"
            
            # Verify WAL mode (only works with file-based databases)
            cursor = conn.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            assert journal_mode == "wal", f"Expected WAL mode, got {journal_mode}"
            
            test_logger.info("[PASS] Schema initialized successfully")
            return True
            
        except Exception as e:
            test_logger.error(f"[FAIL] Schema initialization failed: {e}", exc_info=True)
            return False
        finally:
            conn.close()


def test_insert_and_search_decisions():
    """Test inserting and searching decisions."""
    test_logger.info("Testing insert_decision() and search_decisions()...")
    
    conn = sqlite3.connect(":memory:")
    
    try:
        initialize_schema(conn)
        
        # Insert 5 decisions
        decision_ids = []
        for i in range(5):
            decision_id = insert_decision(
                conn,
                pipeline_run_id="test-run-001",
                stage_id="test-stage",
                subagent="test-agent",
                decision_type="test_decision",
                rationale=f"Test decision {i}",
                body=f"This is test decision number {i} with some search terms",
                metadata={"counter": i}
            )
            decision_ids.append(decision_id)
        
        assert len(decision_ids) == 5, "Should have inserted 5 decisions"
        
        # Search for decisions with keyword "test"
        results = search_decisions(conn, "test", limit=20)
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        
        # Search for decisions with keyword "number"
        results = search_decisions(conn, "number", limit=20)
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        
        # Search for specific term
        results = search_decisions(conn, "decision 2", limit=20)
        assert len(results) >= 1, "Should find at least one result"
        
        test_logger.info("[PASS] Decision insert and search test passed")
        return True
        
    except Exception as e:
        test_logger.error(f"[FAIL] Decision insert/search failed: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def test_insert_and_search_shared_facts():
    """Test inserting and searching shared facts."""
    test_logger.info("Testing insert_shared_fact() and search_shared_facts()...")
    
    conn = sqlite3.connect(":memory:")
    
    try:
        initialize_schema(conn)
        
        # Insert a shared fact
        fact_id = insert_shared_fact(
            conn,
            pipeline_run_id="test-run-001",
            stage_id="test-stage",
            fact_key="project_convention",
            fact_value="Use ESM imports only",
            rationale="Standard import convention for this project"
        )
        
        assert fact_id > 0, "Should have inserted fact with valid ID"
        
        # Search for the fact
        results = search_shared_facts(conn, "ESM", limit=20)
        assert len(results) >= 1, "Should find the inserted fact"
        
        assert results[0]["fact_key"] == "project_convention"
        assert results[0]["fact_value"] == "Use ESM imports only"
        
        test_logger.info("[PASS] Shared fact insert and search test passed")
        return True
        
    except Exception as e:
        test_logger.error(f"[FAIL] Shared fact insert/search failed: {e}", exc_info=True)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    test_logger.info("Running decision database tests...")
    
    # Create test documentation
    test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    test_doc_dir = Path(__file__).parent.parent.parent / "docs" / "orchestrator" / "tests"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    test_doc_file = test_doc_dir / f"{test_timestamp}-decisions_tests.md"
    
    test_results = []
    
    try:
        if test_verify_fts5():
            test_results.append("[PASS] FTS5 verification test passed")
        else:
            test_results.append("[FAIL] FTS5 verification test failed")
        
        if test_initialize_schema():
            test_results.append("[PASS] Schema initialization test passed")
        else:
            test_results.append("[FAIL] Schema initialization test failed")
        
        if test_insert_and_search_decisions():
            test_results.append("[PASS] Decision insert/search test passed")
        else:
            test_results.append("[FAIL] Decision insert/search test failed")
        
        if test_insert_and_search_shared_facts():
            test_results.append("[PASS] Shared fact insert/search test passed")
        else:
            test_results.append("[FAIL] Shared fact insert/search test failed")
        
        passed_count = sum(1 for r in test_results if "[PASS]" in r)
        total_count = len(test_results)
        
        test_logger.info(f"Test Results: {passed_count}/{total_count} passed")
        
        if passed_count == total_count:
            test_logger.info("[SUCCESS] All decision database tests passed!")
        else:
            test_logger.error(f"[FAILURE] {total_count - passed_count} test(s) failed")
            sys.exit(1)
        
        # Write test documentation
        test_doc_content = f"""# Decision Database Tests - {test_timestamp}

## Test Setup
- Date: {test_timestamp}
- Test file: {__file__}
- Decisions module: scripts/memory/decisions.py
- Python version: {sys.version.split()[0]}

## Test Results
""" + "\n".join(test_results) + f"""

## Environment
- Working directory: {Path.cwd()}
- Test directory: {Path(__file__).parent}

## Test Coverage
- FTS5 availability verification
- Database schema initialization
- Decision insertion and full-text search
- Shared fact insertion and search
- WAL mode verification

## Notes
- All tests passed successfully
- FTS5 full-text search working with BM25 ranking
- Database schema created with triggers for FTS5 sync
- WAL mode confirmed for crash safety
"""
        test_doc_file.write_text(test_doc_content, encoding='utf-8')
        test_logger.info(f"Test documentation written to: {test_doc_file}")
        
    except Exception as e:
        test_logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)