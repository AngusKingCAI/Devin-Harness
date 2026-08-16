"""Main orchestrator entry point for Devin CLI Orchestrator."""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional
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

logger = setup_logging("orchestrator.main")

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from state.state import WorkflowState, StateMachine, atomic_write_state, OrchestratorLock
from pipeline.pipeline import PipelineConfig
from orchestrator.subprocess_runner import run_stage

# Configuration with environment variable support
PROJECT_ROOT = Path(os.environ.get('ORCHESTRATOR_PROJECT_ROOT', Path.cwd()))
STATE_PATH = Path(os.environ.get('ORCHESTRATOR_STATE_PATH', PROJECT_ROOT / '.devin' / 'state' / 'workflow-state.json'))
PIPELINE_CONFIG_PATH = Path(os.environ.get('ORCHESTRATOR_PIPELINE_CONFIG_PATH', PROJECT_ROOT / '.devin' / 'config' / 'pipeline' / 'pipeline.json'))
LOCK_PATH = Path(os.environ.get('ORCHESTRATOR_LOCK_PATH', PROJECT_ROOT / '.devin' / 'state' / 'orchestrator.lock'))

def load_pipeline_config() -> PipelineConfig:
    """Load pipeline configuration."""
    if not PIPELINE_CONFIG_PATH.exists():
        raise RuntimeError(f"Pipeline config not found: {PIPELINE_CONFIG_PATH}")
    
    with open(PIPELINE_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    
    return PipelineConfig(**config_data)

def initialize_workflow_state(pipeline_config: PipelineConfig) -> WorkflowState:
    """Initialize workflow state from pipeline config."""
    # Initialize stage states
    stage_states = {}
    for stage in pipeline_config.stages:
        stage_states[stage.id] = {
            'status': 'pending',
            'subagent': stage.subagent,
            'task_path': stage.task_path,
            'output_paths': [],
            'recovery_message': '',
            'recovery_brief_needed': False,
            'human_approval_required': stage.human_approval_required if hasattr(stage, 'human_approval_required') else False
        }
    
    # Initialize workflow state
    state = WorkflowState(
        pipeline_id=pipeline_config.id,
        pipeline_run_id=f"{pipeline_config.id}-{datetime.now(timezone.utc).timestamp()}",
        status='initialized',
        current_stage_id=pipeline_config.stages[0].id if pipeline_config.stages else None,
        stage_states=stage_states,
        shared_context={},
        checkpoints={}
    )
    
    return state

def run_orchestrator(resume: bool = False):
    """Run the orchestrator."""
    # Load pipeline config
    pipeline_config = load_pipeline_config()
    
    # Acquire lock
    lock = OrchestratorLock(str(LOCK_PATH))
    try:
        lock.acquire()
    except RuntimeError as e:
        print(f"Failed to acquire lock: {e}")
        sys.exit(1)
    
    try:
        # Load or initialize workflow state
        if resume and STATE_PATH.exists():
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            state = WorkflowState(**state_data)
            print(f"Resuming workflow: {state.pipeline_run_id}")
        else:
            state = initialize_workflow_state(pipeline_config)
            atomic_write_state(state, str(STATE_PATH))
            print(f"Initialized workflow: {state.pipeline_run_id}")
        
        # Create state machine
        state_machine = StateMachine(state)
        
        # Run stages
        for stage in pipeline_config.stages:
            stage_id = stage.id
            
            # Check if stage is already completed
            stage_state = state.stage_states.get(stage_id, {})
            if stage_state.get('status') == 'completed':
                print(f"Stage {stage_id} already completed, skipping")
                continue
            
            # Set current stage
            state_machine.set_current_stage(stage_id)
            atomic_write_state(state, str(STATE_PATH))
            
            # Run stage
            print(f"Running stage {stage_id} with subagent {stage.subagent}...")
            
            # Build task from task file
            task_path = PROJECT_ROOT / stage.task_path
            if not task_path.exists():
                print(f"Task file not found: {task_path}")
                stage_state['status'] = 'failed'
                stage_state['error'] = f"Task file not found: {task_path}"
                state.stage_states[stage_id] = stage_state
                atomic_write_state(state, str(STATE_PATH))
                continue
            
            with open(task_path, 'r', encoding='utf-8') as f:
                task = f.read()
            
            # Run stage via subprocess
            try:
                result = run_stage(
                    stage_id=stage_id,
                    subagent=stage.subagent,
                    task=task,
                    session_id=stage_state.get('session_id')
                )
                
                if result['success']:
                    print(f"Stage {stage_id} completed successfully")
                    state_machine.complete_stage(stage_id)
                else:
                    print(f"Stage {stage_id} failed with exit code {result['exit_code']}")
                    state_machine.fail_stage(stage_id, result.get('stderr', 'Unknown error'))
                
                atomic_write_state(state, str(STATE_PATH))
                
            except Exception as e:
                print(f"Error running stage {stage_id}: {e}")
                state_machine.fail_stage(stage_id, str(e))
                atomic_write_state(state, str(STATE_PATH))
                continue
        
        # Mark workflow as completed
        state.status = 'completed'
        state.completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        atomic_write_state(state, str(STATE_PATH))
        
        print(f"Workflow {state.pipeline_run_id} completed")
        
    finally:
        lock.release()

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Devin CLI Orchestrator')
    parser.add_argument('--resume', action='store_true', help='Resume from existing workflow state')
    parser.add_argument('--stage', type=str, help='Run specific stage')
    
    args = parser.parse_args()
    
    try:
        if args.stage:
            # Run specific stage
            pipeline_config = load_pipeline_config()
            stage = next((s for s in pipeline_config.stages if s.id == args.stage), None)
            
            if not stage:
                print(f"Stage not found: {args.stage}")
                sys.exit(1)
            
            task_path = PROJECT_ROOT / stage.task_path
            if not task_path.exists():
                print(f"Task file not found: {task_path}")
                sys.exit(1)
            
            with open(task_path, 'r', encoding='utf-8') as f:
                task = f.read()
            
            result = run_stage(
                stage_id=stage.id,
                subagent=stage.subagent,
                task=task
            )
            
            sys.exit(0 if result['success'] else 1)
        else:
            # Run full orchestrator
            run_orchestrator(resume=args.resume)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()