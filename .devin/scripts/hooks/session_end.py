"""SessionEnd hook script for Devin CLI Orchestrator."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

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
    # Read hook payload from stdin
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error parsing hook payload: {e}\n")
        sys.exit(1)
    
    session_id = payload.get('session_id')
    end_reason = payload.get('end_reason', 'unknown')
    
    # Read workflow state
    state = read_workflow_state()
    
    if not state:
        sys.stderr.write("Workflow state not found\n")
        sys.exit(1)
    
    current_stage_id = state.get('current_stage_id')
    current_stage_state = state.get('stage_states', {}).get(current_stage_id, {})
    
    # Mark stage as completed or stopped based on end reason
    if end_reason == 'completed':
        current_stage_state['status'] = 'completed'
        current_stage_state['completed_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        current_stage_state['status'] = 'stopped'
        current_stage_state['stopped_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        current_stage_state['stop_reason'] = end_reason
    
    state['stage_states'][current_stage_id] = current_stage_state
    write_workflow_state(state)
    
    # Audit the event
    audit_payload = {
        "session_id": session_id,
        "stage_id": current_stage_id,
        "end_reason": end_reason,
        "status": current_stage_state['status']
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
    
    append_audit_event("SessionEnd", audit_payload, prev_hash)
    
    # No output needed for SessionEnd hook

if __name__ == "__main__":
    main()