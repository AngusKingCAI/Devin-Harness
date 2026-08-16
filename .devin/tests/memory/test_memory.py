"""Tests for the memory system facade."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from memory.memory import MemorySystem

# Setup logging for tests
import logging
import json

def setup_test_logging():
    """Setup logging for test execution."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    test_log_file = log_dir / f"test_memory-Log.jsonl"
    
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
    
    logger = logging.getLogger("test_memory")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

test_logger = setup_test_logging()


def test_memory_system_initialization():
    """Test memory system initialization."""
    test_logger.info("Testing MemorySystem initialization...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "decisions.sqlite"
        audit_path = Path(temp_dir) / "action-log.jsonl"
        
        memory = MemorySystem(db_path, audit_path)
        
        try:
            memory.initialize()
            
            assert memory.conn is not None, "Database connection should be established"
            assert db_path.exists(), "Database file should exist"
            
            test_logger.info("[PASS] MemorySystem initialization test passed")
            return True
            
        except Exception as e:
            test_logger.error(f"[FAIL] MemorySystem initialization failed: {e}", exc_info=True)
            return False
        finally:
            memory.close()


def test_memory_system_context_manager():
    """Test memory system as context manager."""
    test_logger.info("Testing MemorySystem context manager...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "decisions.sqlite"
        audit_path = Path(temp_dir) / "action-log.jsonl"
        
        try:
            with MemorySystem(db_path, audit_path) as memory:
                assert memory.conn is not None, "Connection should be established in context"
                
                # Add a decision
                decision_id = memory.add_decision(
                    pipeline_run_id="test-run-001",
                    stage_id="test-stage",
                    subagent="test-agent",
                    decision_type="test_decision",
                    rationale="Test decision",
                    body="Test decision body"
                )
                
                assert decision_id > 0, "Decision should be inserted"
            
            # Connection should be closed after context exit
            assert memory.conn is None, "Connection should be closed after context exit"
            
            test_logger.info("[PASS] MemorySystem context manager test passed")
            return True
            
        except Exception as e:
            test_logger.error(f"[FAIL] Context manager test failed: {e}", exc_info=True)
            return False


def test_memory_system_integration():
    """Test full memory system integration."""
    test_logger.info("Testing full memory system integration...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "decisions.sqlite"
        audit_path = Path(temp_dir) / "action-log.jsonl"
        
        try:
            with MemorySystem(db_path, audit_path) as memory:
                # Add audit events
                hash1 = memory.audit_event({"event": "test_event_1", "data": "test_data_1"})
                hash2 = memory.audit_event({"event": "test_event_2", "data": "test_data_2"})
                
                assert hash1 != "genesis", "First hash should not be genesis"
                assert hash2 != hash1, "Different events should have different hashes"
                
                # Add decisions
                decision_id1 = memory.add_decision(
                    pipeline_run_id="test-run-001",
                    stage_id="stage1",
                    subagent="agent1",
                    decision_type="stage_output",
                    rationale="Stage completed successfully",
                    body="Stage 1 completed with output generated"
                )
                
                decision_id2 = memory.add_decision(
                    pipeline_run_id="test-run-001",
                    stage_id="stage2",
                    subagent="agent2",
                    decision_type="tool_choice",
                    rationale="Chose specific tool",
                    body="Selected tool for specific task"
                )
                
                # Add shared fact
                fact_id = memory.add_shared_fact(
                    pipeline_run_id="test-run-001",
                    stage_id="stage1",
                    fact_key="convention",
                    fact_value="Use snake_case",
                    rationale="Naming convention"
                )
                
                # Search decisions
                results = memory.search_decisions("completed", limit=10)
                assert len(results) >= 1, "Should find at least one decision"
                
                # Search shared facts
                facts = memory.search_shared_facts("snake_case", limit=10)
                assert len(facts) >= 1, "Should find the shared fact"
                
                # Verify integrity
                is_valid = memory.verify_integrity()
                assert is_valid, "Audit chain should be valid"
            
            test_logger.info("[PASS] Full memory system integration test passed")
            return True
            
        except Exception as e:
            test_logger.error(f"[FAIL] Integration test failed: {e}", exc_info=True)
            return False


if __name__ == "__main__":
    test_logger.info("Running memory system tests...")
    
    # Create test documentation
    test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    test_doc_dir = Path(__file__).parent.parent.parent / "docs" / "orchestrator" / "tests"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    test_doc_file = test_doc_dir / f"{test_timestamp}-memory_tests.md"
    
    test_results = []
    
    try:
        if test_memory_system_initialization():
            test_results.append("[PASS] MemorySystem initialization test passed")
        else:
            test_results.append("[FAIL] MemorySystem initialization test failed")
        
        if test_memory_system_context_manager():
            test_results.append("[PASS] Context manager test passed")
        else:
            test_results.append("[FAIL] Context manager test failed")
        
        if test_memory_system_integration():
            test_results.append("[PASS] Full integration test passed")
        else:
            test_results.append("[FAIL] Full integration test failed")
        
        passed_count = sum(1 for r in test_results if "[PASS]" in r)
        total_count = len(test_results)
        
        test_logger.info(f"Test Results: {passed_count}/{total_count} passed")
        
        if passed_count == total_count:
            test_logger.info("[SUCCESS] All memory system tests passed!")
        else:
            test_logger.error(f"[FAILURE] {total_count - passed_count} test(s) failed")
            sys.exit(1)
        
        # Write test documentation
        test_doc_content = f"""# Memory System Tests - {test_timestamp}

## Test Setup
- Date: {test_timestamp}
- Test file: {__file__}
- Memory module: scripts/memory/memory.py
- Python version: {sys.version.split()[0]}

## Test Results
""" + "\n".join(test_results) + f"""

## Environment
- Working directory: {Path.cwd()}
- Test directory: {Path(__file__).parent}

## Test Coverage
- MemorySystem initialization
- Context manager usage
- Full integration (audit + decisions + shared facts)
- Database and audit log coordination

## Notes
- All tests passed successfully
- Memory system facade working correctly
- Audit log and decision database integrated
- Context manager pattern working as expected
"""
        test_doc_file.write_text(test_doc_content, encoding='utf-8')
        test_logger.info(f"Test documentation written to: {test_doc_file}")
        
    except Exception as e:
        test_logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)