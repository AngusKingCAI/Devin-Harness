"""PermissionRequest hook script for Devin CLI Orchestrator."""

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

logger = setup_logging("hooks.permission_request")

# Configuration with environment variable support
PROJECT_ROOT = Path(os.environ.get('ORCHESTRATOR_PROJECT_ROOT', Path.cwd()))
STATE_PATH = Path(os.environ.get('ORCHESTRATOR_STATE_PATH', PROJECT_ROOT / '.devin' / 'state' / 'workflow-state.json'))
AUDIT_LOG_PATH = Path(os.environ.get('ORCHESTRATOR_AUDIT_LOG_PATH', PROJECT_ROOT / '.devin' / 'state' / 'action-log.jsonl'))
POLICY_PATH = Path(os.environ.get('ORCHESTRATOR_POLICY_PATH', PROJECT_ROOT / '.devin' / 'config' / 'policy.json'))

def read_workflow_state():
    """Read workflow state from disk."""
    if not STATE_PATH.exists():
        return None
    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def read_policy():
    """Read policy configuration."""
    if not POLICY_PATH.exists():
        return {}
    with open(POLICY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

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
    logger.info("PermissionRequest hook triggered")
    
    # Read hook payload from stdin
    try:
        payload = json.load(sys.stdin)
        logger.debug(f"Hook payload received: {payload}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing hook payload: {e}", exc_info=True)
        sys.stderr.write(f"Error parsing hook payload: {e}\n")
        sys.exit(1)
    
    tool_name = payload.get('tool_name')
    
    # Read policy for permission lists
    policy = read_policy()
    always_allow = policy.get('always_allow_tools', [])
    always_deny = policy.get('always_deny_tools', [])
    
    # Read workflow state to check human approval requirement
    state = read_workflow_state()
    human_approval_required = False
    
    if state:
        current_stage_id = state.get('current_stage_id')
        current_stage_state = state.get('stage_states', {}).get(current_stage_id, {})
        human_approval_required = current_stage_state.get('human_approval_required', False)
    
    output = {}
    
    # Check always-allow list
    if tool_name in always_allow:
        output = {
            "decision": "approve"
        }
    # Check always-deny list
    elif tool_name in always_deny:
        output = {
            "decision": "block",
            "reason": f"Tool '{tool_name}' is in always-deny list"
        }
    # Check human approval requirement
    elif human_approval_required:
        # Return nothing to fall through to interactive prompt
        output = {}
    # Default: approve
    else:
        output = {
            "decision": "approve"
        }
    
    # Audit the permission request
    audit_payload = {
        "tool_name": tool_name,
        "decision": output.get('decision', 'pending'),
        "human_approval_required": human_approval_required
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
    
    append_audit_event("PermissionRequest", audit_payload, prev_hash)
    
    # Output hook response
    if output:
        json.dump(output, sys.stdout)
        sys.stdout.write('\n')

if __name__ == "__main__":
    main()