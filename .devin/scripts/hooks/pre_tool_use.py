"""PreToolUse hook script for Devin CLI Orchestrator."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

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
    # Read hook payload from stdin
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error parsing hook payload: {e}\n")
        sys.exit(1)
    
    tool_name = payload.get('tool_name')
    tool_input = payload.get('tool_input', {})
    
    # Read policy for denylist (basic implementation)
    policy = read_policy()
    denylist = policy.get('destructive_commands', [])
    
    output = {}
    
    # Check for destructive commands
    if tool_name == "exec" and denylist:
        command = tool_input.get('command', '')
        for destructive_pattern in denylist:
            if destructive_pattern in command:
                output = {
                    "decision": "block",
                    "reason": f"Command matches destructive pattern: {destructive_pattern}"
                }
                # Audit the blocked command
                audit_payload = {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "decision": "block",
                    "reason": output["reason"]
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
                append_audit_event("PreToolUse", audit_payload, prev_hash)
                json.dump(output, sys.stdout)
                sys.stdout.write('\n')
                sys.exit(2)  # Exit code 2 for blocked commands
    
    # Audit the tool use
    audit_payload = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "decision": "allow"
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
    
    append_audit_event("PreToolUse", audit_payload, prev_hash)
    
    # Output hook response (empty for allow)
    if output:
        json.dump(output, sys.stdout)
        sys.stdout.write('\n')

if __name__ == "__main__":
    main()