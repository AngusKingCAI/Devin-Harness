"""UserPromptSubmit hook script for Devin CLI Orchestrator."""

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

logger = setup_logging("hooks.user_prompt_submit")

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

def build_recovery_brief(stage_id, state):
    """Build recovery brief for stage."""
    # Get prior stage outputs
    prior_outputs = {}
    for stage_name, stage_state in state.get('stage_states', {}).items():
        if stage_name != stage_id and stage_state.get('output_paths'):
            prior_outputs[stage_name] = stage_state['output_paths']
    
    # Get shared context
    shared_context = state.get('shared_context', {})
    
    # Get recovery message
    recovery_message = state.get('stage_states', {}).get(stage_id, {}).get('recovery_message', '')
    
    # Build brief
    brief_parts = [
        f"RECOVERY BRIEF:",
        f"- You are in stage '{stage_id}' (subagent: {state.get('stage_states', {}).get(stage_id, {}).get('subagent', 'unknown')}).",
        f"- Recovery message: {recovery_message}",
        f"- Prior stage outputs: {json.dumps(prior_outputs, indent=2)}",
        f"- Shared context: {json.dumps(shared_context, indent=2)}"
    ]
    
    return '\n'.join(brief_parts)

def search_relevant_decisions(stage_id, subagent, limit=5):
    """Search for relevant past decisions using FTS5."""
    try:
        import sqlite3
        if not DECISIONS_DB_PATH.exists():
            return []
        
        conn = sqlite3.connect(str(DECISIONS_DB_PATH))
        cursor = conn.execute(
            """SELECT id, rationale, body, bm25(decisions_fts) AS score
               FROM decisions_fts
               JOIN decisions d ON decisions_fts.rowid = d.id
               WHERE decisions_fts MATCH ?
               ORDER BY score
               LIMIT ?""",
            (f"{stage_id} {subagent} decision", limit)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "rationale": row[1],
                "body": row[2],
                "score": row[3]
            })
        
        conn.close()
        return results
    except Exception as e:
        sys.stderr.write(f"Error searching decisions: {e}\n")
        return []

def main():
    """Main hook entry point."""
    logger.info("UserPromptSubmit hook triggered")
    
    # Read hook payload from stdin
    try:
        payload = json.load(sys.stdin)
        logger.debug(f"Hook payload received: {payload}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing hook payload: {e}", exc_info=True)
        sys.stderr.write(f"Error parsing hook payload: {e}\n")
        sys.exit(1)
    
    session_id = payload.get('session_id')
    prompt_id = payload.get('prompt_id')
    stage_id = os.environ.get('ORCHESTRATOR_STAGE_ID')
    
    # Read workflow state
    state = read_workflow_state()
    
    if not state:
        sys.stderr.write("Workflow state not found\n")
        sys.exit(1)
    
    # Get current stage from state
    current_stage_id = state.get('current_stage_id')
    current_stage_state = state.get('stage_states', {}).get(current_stage_id, {})
    
    if not current_stage_id:
        sys.stderr.write(f"Current stage not found in workflow state\n")
        sys.exit(1)
    
    # Check for recovery brief needed
    recovery_brief_needed = current_stage_state.get('recovery_brief_needed', False)
    
    output = {}
    
    if recovery_brief_needed:
        # Build recovery brief
        brief = build_recovery_brief(current_stage_id, state)
        
        # Search for relevant decisions
        decisions = search_relevant_decisions(
            current_stage_id,
            current_stage_state.get('subagent', ''),
            limit=5
        )
        
        if decisions:
            brief += "\n- Relevant past decisions:\n"
            for i, decision in enumerate(decisions, 1):
                brief += f"  {i}. [{decision['rationale']}] {decision['body'][:100]}...\n"
        
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": brief
            }
        }
        
        # Clear recovery brief flag
        current_stage_state['recovery_brief_needed'] = False
        state['stage_states'][current_stage_id] = current_stage_state
        write_workflow_state(state)
    
    # Audit the event
    audit_payload = {
        "session_id": session_id,
        "prompt_id": prompt_id,
        "stage_id": current_stage_id,
        "recovery_brief_injected": recovery_brief_needed
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
    
    append_audit_event("UserPromptSubmit", audit_payload, prev_hash)
    
    # Output hook response
    if output:
        json.dump(output, sys.stdout)
        sys.stdout.write('\n')

if __name__ == "__main__":
    main()