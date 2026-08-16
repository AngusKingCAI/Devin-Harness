"""Stop hook script for Devin CLI Orchestrator."""

import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

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

logger = setup_logging("hooks.stop")

# Configuration with environment variable support
PROJECT_ROOT = Path(os.environ.get('ORCHESTRATOR_PROJECT_ROOT', Path.cwd()))
STATE_PATH = Path(os.environ.get('ORCHESTRATOR_STATE_PATH', PROJECT_ROOT / '.devin' / 'state' / 'workflow-state.json'))
AUDIT_LOG_PATH = Path(os.environ.get('ORCHESTRATOR_AUDIT_LOG_PATH', PROJECT_ROOT / '.devin' / 'state' / 'action-log.jsonl'))

def read_workflow_state():
    """Read workflow state from disk."""
    if not STATE_PATH.exists():
        return None
    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_workflow_state(state):
    """Write workflow state to disk."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)

def append_audit_event(event_type, payload, prev_hash="genesis"):
    """Append event to audit log."""
    import hashlib
    
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prev_hash": prev_hash,
        "hook_event": event_type,
        "payload": payload
    }
    
    record_content = json.dumps(record, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(record_content.encode('utf-8')).hexdigest()
    record["hash"] = current_hash
    
    with open(AUDIT_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    return current_hash

def main():
    """Main hook entry point."""
    logger.info("Stop hook triggered")
    
    # Read hook payload from stdin
    try:
        payload = json.load(sys.stdin)
        logger.debug(f"Hook payload received: {payload}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing hook payload: {e}", exc_info=True)
        sys.stderr.write(f"Error parsing hook payload: {e}\n")
        sys.exit(1)
    
    stop_reason = payload.get('stop_reason', 'unknown')
    
    # Read workflow state
    state = read_workflow_state()
    
    if not state:
        sys.stderr.write("Workflow state not found\n")
        sys.exit(1)
    
    current_stage_id = state.get('current_stage_id')
    current_stage_state = state.get('stage_states', {}).get(current_stage_id, {})
    
    # Mark stage as stopped (not completed)
    current_stage_state['status'] = 'stopped'
    current_stage_state['stopped_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    current_stage_state['stop_reason'] = stop_reason
    
    state['stage_states'][current_stage_id] = current_stage_state
    write_workflow_state(state)
    
    # Audit the event
    audit_payload = {
        "stage_id": current_stage_id,
        "stop_reason": stop_reason,
        "timestamp": current_stage_state['stopped_at']
    }
    
    # Get previous hash from audit log
    prev_hash = "genesis"
    if AUDIT_LOG_PATH.exists():
        try:
            with open(AUDIT_LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    last_line = json.loads(lines[-1].strip())
                    prev_hash = last_line.get('hash', 'genesis')
        except:
            pass
    
    append_audit_event("Stop", audit_payload, prev_hash)
    
    # No output needed for Stop hook

if __name__ == "__main__":
    main()