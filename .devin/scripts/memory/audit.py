"""Audit log system with SHA-256 hash chain for integrity verification."""

import logging
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Setup logging for this module
def setup_logging(module_name: str):
    """Setup JSONL logging for a module."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"{module_name}-Log.jsonl"
    
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
    
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging(__name__)


def compute_hash(content: str) -> str:
    """
    Compute SHA-256 hash of content.
    
    Args:
        content: String content to hash
        
    Returns:
        Hexadecimal SHA-256 hash
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def append_audit(path: Path, payload: Dict[str, Any], prev_hash: str) -> str:
    """
    Append an audit record to the log with hash chain.
    
    Args:
        path: Path to the audit log file (JSONL)
        payload: Dictionary payload to append
        prev_hash: Previous hash in the chain (or "genesis" for first record)
        
    Returns:
        The hash of this record
    """
    logger.info(f"Appending audit record to: {path}")
    
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create record with hash chain
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prev_hash": prev_hash,
        "payload": payload
    }
    
    # Compute hash of this record (excluding the hash field)
    record_content = json.dumps(record, sort_keys=True, ensure_ascii=False)
    current_hash = compute_hash(record_content)
    
    # Add hash to record
    record["hash"] = current_hash
    
    # Append to file
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    logger.debug(f"Appended audit record with hash: {current_hash}")
    return current_hash


def verify_audit_chain(path: Path) -> bool:
    """
    Verify the integrity of the audit log by walking the hash chain.
    
    Args:
        path: Path to the audit log file (JSONL)
        
    Returns:
        True if chain is valid
        
    Raises:
        ValueError: If chain is broken or tampered
    """
    logger.info(f"Verifying audit chain: {path}")
    
    if not path.exists():
        logger.warning(f"Audit log does not exist: {path}")
        return True  # Empty log is valid
    
    prev_hash = "genesis"
    line_number = 0
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line_number += 1
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                
                # Verify record structure
                if "hash" not in record:
                    raise ValueError(f"Line {line_number}: Missing 'hash' field")
                if "prev_hash" not in record:
                    raise ValueError(f"Line {line_number}: Missing 'prev_hash' field")
                
                # Verify chain continuity
                if record["prev_hash"] != prev_hash:
                    raise ValueError(
                        f"Line {line_number}: Chain broken. Expected prev_hash={prev_hash}, "
                        f"got prev_hash={record['prev_hash']}"
                    )
                
                # Verify hash integrity
                record_copy = record.copy()
                stored_hash = record_copy.pop("hash")
                expected_hash = compute_hash(json.dumps(record_copy, sort_keys=True, ensure_ascii=False))
                
                if stored_hash != expected_hash:
                    raise ValueError(
                        f"Line {line_number}: Hash mismatch. Expected {expected_hash}, "
                        f"got {stored_hash}"
                    )
                
                prev_hash = stored_hash
                
            except json.JSONDecodeError as e:
                raise ValueError(f"Line {line_number}: Invalid JSON: {e}")
    
    logger.info(f"Audit chain verified successfully ({line_number} records)")
    return True