"""Subprocess runner for Devin CLI Orchestrator."""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
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

logger = setup_logging("orchestrator.subprocess_runner")

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

def build_environment(stage_id: str, subagent: str, session_id: str) -> Dict[str, str]:
    """Build environment variables for subprocess."""
    env = os.environ.copy()
    
    # Set orchestrator environment variables
    env['ORCHESTRATOR_PROJECT_ROOT'] = str(PROJECT_ROOT)
    env['ORCHESTRATOR_STATE_PATH'] = str(STATE_PATH)
    env['ORCHESTRATOR_AUDIT_LOG_PATH'] = str(AUDIT_LOG_PATH)
    env['ORCHESTRATOR_DECISIONS_DB_PATH'] = str(DECISIONS_DB_PATH)
    env['ORCHESTRATOR_STAGE_ID'] = stage_id
    env['ORCHESTRATOR_SUBAGENT'] = subagent
    env['ORCHESTRATOR_SESSION_ID'] = session_id
    
    return env

def run_stage(stage_id: str, subagent: str, task: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Run a pipeline stage as a subprocess."""
    # Read workflow state
    state = read_workflow_state()
    
    if not state:
        raise RuntimeError("Workflow state not found")
    
    # Generate session ID if not provided
    if not session_id:
        session_id = f"{stage_id}-{datetime.now(timezone.utc).timestamp()}"
    
    # Update stage state
    stage_state = state.get('stage_states', {}).get(stage_id, {})
    stage_state['subagent'] = subagent
    stage_state['session_id'] = session_id
    stage_state['status'] = 'running'
    stage_state['started_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stage_state['heartbeat'] = {
        'last_beat_at': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    
    state['stage_states'][stage_id] = stage_state
    state['current_stage_id'] = stage_id
    write_workflow_state(state)
    
    # Build environment
    env = build_environment(stage_id, subagent, session_id)
    
    # Build devin CLI command
    cmd = [
        'devin',
        '--agent', subagent,
        task
    ]
    
    # Run subprocess
    print(f"Running stage {stage_id} with subagent {subagent}...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        # Update stage state with result
        stage_state['status'] = 'completed' if process.returncode == 0 else 'failed'
        stage_state['completed_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        stage_state['exit_code'] = process.returncode
        stage_state['stdout'] = stdout
        stage_state['stderr'] = stderr
        
        state['stage_states'][stage_id] = stage_state
        write_workflow_state(state)
        
        return {
            'success': process.returncode == 0,
            'exit_code': process.returncode,
            'stdout': stdout,
            'stderr': stderr,
            'session_id': session_id
        }
        
    except Exception as e:
        # Update stage state with error
        stage_state['status'] = 'failed'
        stage_state['error'] = str(e)
        state['stage_states'][stage_id] = stage_state
        write_workflow_state(state)
        
        raise

def main():
    """Main entry point for subprocess runner."""
    if len(sys.argv) < 4:
        print("Usage: python subprocess_runner.py <stage_id> <subagent> <task> [session_id]")
        sys.exit(1)
    
    stage_id = sys.argv[1]
    subagent = sys.argv[2]
    task = sys.argv[3]
    session_id = sys.argv[4] if len(sys.argv) > 4 else None
    
    try:
        result = run_stage(stage_id, subagent, task, session_id)
        print(f"Stage {stage_id} completed: {result['success']}")
        sys.exit(0 if result['success'] else 1)
    except Exception as e:
        print(f"Error running stage {stage_id}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()