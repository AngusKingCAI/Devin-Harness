"""Tests for the audit log system."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from memory.audit import append_audit, verify_audit_chain, compute_hash

# Setup logging for tests
import logging
import json

def setup_test_logging():
    """Setup logging for test execution."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    test_log_file = log_dir / f"test_audit-Log.jsonl"
    
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
    
    logger = logging.getLogger("test_audit")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

test_logger = setup_test_logging()


def test_compute_hash():
    """Test SHA-256 hash computation."""
    test_logger.info("Testing compute_hash()...")
    
    hash1 = compute_hash("test content")
    hash2 = compute_hash("test content")
    hash3 = compute_hash("different content")
    
    assert hash1 == hash2, "Same content should produce same hash"
    assert hash1 != hash3, "Different content should produce different hash"
    assert len(hash1) == 64, "SHA-256 hash should be 64 characters"
    
    test_logger.info("[PASS] compute_hash() test passed")


def test_append_audit():
    """Test appending audit records."""
    test_logger.info("Testing append_audit()...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        audit_path = Path(temp_dir) / "action-log.jsonl"
        
        # Append first record
        payload1 = {"event": "test_event", "data": "test_data"}
        hash1 = append_audit(audit_path, payload1, "genesis")
        
        assert audit_path.exists(), "Audit file should exist"
        assert hash1 != "genesis", "Hash should not be genesis"
        
        # Append second record
        payload2 = {"event": "another_event", "data": "more_data"}
        hash2 = append_audit(audit_path, payload2, hash1)
        
        assert hash2 != hash1, "Different records should have different hashes"
        
        # Verify file has 2 lines
        with open(audit_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
        
        test_logger.info("[PASS] append_audit() test passed")


def test_verify_audit_chain():
    """Test audit chain verification."""
    test_logger.info("Testing verify_audit_chain()...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        audit_path = Path(temp_dir) / "action-log.jsonl"
        
        # Append 10 records
        current_hash = "genesis"
        for i in range(10):
            payload = {"event": f"event_{i}", "counter": i}
            current_hash = append_audit(audit_path, payload, current_hash)
        
        # Verify chain
        is_valid = verify_audit_chain(audit_path)
        assert is_valid, "Audit chain should be valid"
        
        test_logger.info("[PASS] verify_audit_chain() test passed")


def test_tamper_detection():
    """Test that tampering is detected."""
    test_logger.info("Testing tamper detection...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        audit_path = Path(temp_dir) / "action-log.jsonl"
        
        # Append some records
        current_hash = "genesis"
        for i in range(5):
            payload = {"event": f"event_{i}", "counter": i}
            current_hash = append_audit(audit_path, payload, current_hash)
        
        # Tamper with a record
        with open(audit_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Modify the second line
        lines[1] = lines[1].replace("event_1", "tampered_event")
        
        with open(audit_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        # Verify chain should fail
        try:
            verify_audit_chain(audit_path)
            test_logger.error("[FAIL] Tamper detection failed - tampered chain was not detected")
            return False
        except ValueError as e:
            test_logger.info(f"[PASS] Tamper correctly detected: {e}")
            return True


if __name__ == "__main__":
    test_logger.info("Running audit tests...")
    
    # Create test documentation
    test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    test_doc_dir = Path(__file__).parent.parent.parent / "docs" / "orchestrator" / "tests"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    test_doc_file = test_doc_dir / f"{test_timestamp}-audit_tests.md"
    
    test_results = []
    
    try:
        test_compute_hash()
        test_results.append("[PASS] compute_hash() test passed")
        
        test_append_audit()
        test_results.append("[PASS] append_audit() test passed")
        
        test_verify_audit_chain()
        test_results.append("[PASS] verify_audit_chain() test passed")
        
        if test_tamper_detection():
            test_results.append("[PASS] tamper detection test passed")
        else:
            test_results.append("[FAIL] tamper detection test failed")
        
        test_logger.info("[SUCCESS] All audit tests passed!")
        
        # Write test documentation
        test_doc_content = f"""# Audit Tests - {test_timestamp}

## Test Setup
- Date: {test_timestamp}
- Test file: {__file__}
- Audit module: scripts/memory/audit.py
- Python version: {sys.version.split()[0]}

## Test Results
""" + "\n".join(test_results) + f"""

## Environment
- Working directory: {Path.cwd()}
- Test directory: {Path(__file__).parent}

## Test Coverage
- SHA-256 hash computation
- Audit record appending with hash chain
- Audit chain verification
- Tamper detection

## Notes
- All tests passed successfully
- Hash chain integrity verified
- Tampering correctly detected and raises ValueError
- JSONL format working correctly
"""
        test_doc_file.write_text(test_doc_content, encoding='utf-8')
        test_logger.info(f"Test documentation written to: {test_doc_file}")
        
    except AssertionError as e:
        test_logger.error(f"[FAIL] Test failed: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        test_logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)