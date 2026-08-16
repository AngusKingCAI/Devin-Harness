"""PostToolUse hook script for Devin CLI Orchestrator."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Configuration with environment variable support
PROJECT_ROOT = Path(os.environ.get('ORCHESTRATOR_PROJECT_ROOT', Path.cwd()))
STATE_PATH = Path(os.environ.get('ORCHESTRATOR_STATE_PATH', PROJECT_ROOT / '.devin' / 'state' / 'workflow-state.json'))
AUDIT_LOG_PATH = Path(os.environ.get('ORCHESTRATOR_AUDIT_LOG_PATH', PROJECT_ROOT / '.devin' / 'state' / 'action-log.jsonl'))
DECISIONS_DB_PATH = Path(os.environ.get('ORCHESTRATOR_DECISIONS_DB_PATH', PROJECT_ROOT / '.devin' / 'state' / 'decisions.sqlite'))

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

def extract_decision_from_tool_call(tool_name, tool_input, tool_response):
    """Extract decision from tool call if applicable."""
    # Heuristic: decision-like tool calls
    decision_keywords = ['decided', 'choice', 'selected', 'chose', 'option']
    
    if tool_name in ['edit', 'write']:
        # These often represent decisions about file changes
        return {
            "rationale": f"Modified file via {tool_name}",
            "body": f"Tool: {tool_name}, Input: {json.dumps(tool_input)[:200]}"
        }
    
    tool_output = str(tool_response)
    if any(keyword in tool_output.lower() for keyword in decision_keywords):
        return {
            "rationale": f"Decision detected in {tool_name} output",
            "body": tool_output[:500]
        }
    
    return None

def extract_shared_fact_from_tool_call(tool_response):
    """Extract shared fact from tool call if applicable."""
    # Heuristic: project-level conventions
    convention_keywords = ['convention', 'standard', 'pattern', 'rule', 'always']
    
    tool_output = str(tool_response)
    if any(keyword in tool_output.lower() for keyword in convention_keywords):
        # Try to extract key-value pattern
        if ':' in tool_output:
            parts = tool_output.split(':', 1)
            if len(parts) == 2:
                return {
                    "fact_key": parts[0].strip(),
                    "fact_value": parts[1].strip(),
                    "rationale": "Extracted from tool output"
                }
    
    return None

def insert_decision(conn, pipeline_run_id, stage_id, subagent, decision_type, rationale, body, metadata=None):
    """Insert decision into database."""
    try:
        import sqlite3
        cursor = conn.execute(
            """
            INSERT INTO decisions (ts, pipeline_run_id, stage_id, subagent, decision_type, rationale, body, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), 
             pipeline_run_id, stage_id, subagent, decision_type, rationale, body, 
             json.dumps(metadata) if metadata else None)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        sys.stderr.write(f"Error inserting decision: {e}\n")
        return None

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
    tool_response = payload.get('tool_response', {})
    
    # Read workflow state
    state = read_workflow_state()
    
    if not state:
        sys.stderr.write("Workflow state not found\n")
        sys.exit(1)
    
    current_stage_id = state.get('current_stage_id')
    current_stage_state = state.get('stage_states', {}).get(current_stage_id, {})
    
    # Update heartbeat
    current_stage_state['heartbeat'] = {
        'last_beat_at': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        'last_stdout_at': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    state['stage_states'][current_stage_id] = current_stage_state
    write_workflow_state(state)
    
    # Extract decision if applicable
    decision = extract_decision_from_tool_call(tool_name, tool_input, tool_response)
    if decision:
        try:
            import sqlite3
            conn = sqlite3.connect(str(DECISIONS_DB_PATH))
            insert_decision(
                conn,
                state.get('pipeline_run_id', 'unknown'),
                current_stage_id,
                current_stage_state.get('subagent', 'unknown'),
                'tool_choice',
                decision['rationale'],
                decision['body']
            )
            conn.close()
        except Exception as e:
            sys.stderr.write(f"Error inserting decision: {e}\n")
    
    # Extract shared fact if applicable
    shared_fact = extract_shared_fact_from_tool_call(tool_response)
    if shared_fact:
        state['shared_context'][shared_fact['fact_key']] = shared_fact['fact_value']
        write_workflow_state(state)
    
    # Check for failed tool response and inject correction
    output = {}
    if tool_response.get('success') == False:
        error_message = tool_response.get('error', 'Unknown error')
        correction = f"The previous command failed with: {error_message}. Consider fixing the error and retrying."
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": correction
            }
        }
    
    # Audit the event
    audit_payload = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
        "decision_extracted": decision is not None,
        "shared_fact_extracted": shared_fact is not None
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
    
    append_audit_event("PostToolUse", audit_payload, prev_hash)
    
    # Output hook response
    if output:
        json.dump(output, sys.stdout)
        sys.stdout.write('\n')

if __name__ == "__main__":
    main()