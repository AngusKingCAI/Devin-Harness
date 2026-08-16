"""State machine and workflow state management."""

import logging
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel, Field, field_validator
from enum import Enum

if TYPE_CHECKING:
    from pipeline.pipeline import PipelineConfig

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


class PipelineStatus(str, Enum):
    """Pipeline status enumeration."""
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ESCALATED = "escalated"


class StageState(str, Enum):
    """Stage state enumeration."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CRASHED_RECOVERABLE = "CRASHED_RECOVERABLE"
    CRASHED_UNRECOVERABLE = "CRASHED_UNRECOVERABLE"
    ESCALATED = "ESCALATED"


class StageStateRecord(BaseModel):
    """State record for a single stage."""
    state: StageState = StageState.PENDING
    subagent: str
    session_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    bounce_count: int = 0
    output_paths: Dict[str, str] = {}
    recovery_brief_needed: bool = False
    recovery_message: Optional[str] = None
    heartbeat: Dict[str, str] = {}
    idempotency_key: Optional[str] = None


class WorkflowState(BaseModel):
    """Workflow state for the entire pipeline."""
    schema_version: str = "1.0"
    pipeline_run_id: str
    pipeline_name: str
    pipeline_version: str
    started_at: str
    last_updated_at: str
    current_stage_id: str
    pipeline_status: PipelineStatus = PipelineStatus.RUNNING
    stage_states: Dict[str, StageStateRecord]
    shared_context: Dict[str, str] = {}
    audit_log_head_hash: str = "genesis"
    compaction_count: int = 0
    last_compaction_at: Optional[str] = None
    
    def validate(self) -> None:
        """Validate the workflow state."""
        if self.current_stage_id not in self.stage_states:
            raise ValueError(f"current_stage_id '{self.current_stage_id}' not found in stage_states")


class StateMachine:
    """Config-driven state machine. Transitions derived from pipeline.json."""
    
    def __init__(self, pipeline_config: Any, initial_state: WorkflowState):
        """
        Initialize state machine with pipeline configuration and initial state.
        
        Args:
            pipeline_config: PipelineConfig object
            initial_state: Initial WorkflowState object
        """
        self.pipeline = pipeline_config
        self.state = initial_state
        
        # Access pipeline properties safely
        pipeline_name = getattr(pipeline_config, 'name', 'unknown')
        stage_count = len(getattr(pipeline_config, 'stages', []))
        
        logger.info(f"Initialized state machine for pipeline '{pipeline_name}' with {stage_count} stages")
    
    def can_transition(self, stage_id: str, event: str) -> bool:
        """
        Check if a transition is valid.
        
        Args:
            stage_id: ID of the stage
            event: Event to check (e.g., 'start', 'complete', 'fail')
            
        Returns:
            True if transition is valid, False otherwise
        """
        logger.debug(f"Checking if stage '{stage_id}' can transition on event '{event}'")
        
        stage_state = self.state.stage_states.get(stage_id)
        if not stage_state:
            logger.warning(f"Stage '{stage_id}' not found in state")
            return False
        
        # Get current state
        current_state = stage_state.state
        
        # Define valid transitions based on event
        valid_transitions = {
            StageState.PENDING: ['start'],
            StageState.RUNNING: ['complete', 'fail', 'crash'],
            StageState.FAILED: ['retry', 'escalate', 'unrecoverable'],
            StageState.CRASHED_RECOVERABLE: ['retry'],
            StageState.COMPLETE: [],
            StageState.REJECTED: ['bounce'],
            StageState.CRASHED_UNRECOVERABLE: [],
            StageState.ESCALATED: []
        }
        
        if current_state not in valid_transitions:
            logger.warning(f"Stage '{stage_id}' in terminal state '{current_state}'")
            return False
        
        if event not in valid_transitions[current_state]:
            logger.warning(f"Event '{event}' not valid for stage '{stage_id}' in state '{current_state}'")
            return False
        
        logger.debug(f"Transition valid: stage '{stage_id}' from '{current_state}' on event '{event}'")
        return True
    
    def transition(self, stage_id: str, event: str) -> WorkflowState:
        """
        Apply a transition and return the new state.
        
        Args:
            stage_id: ID of the stage
            event: Event to apply (e.g., 'start', 'complete', 'fail')
            
        Returns:
            Updated WorkflowState object
        """
        logger.info(f"Transitioning stage '{stage_id}' on event '{event}'")
        
        if not self.can_transition(stage_id, event):
            raise ValueError(f"Invalid transition: stage '{stage_id}' on event '{event}'")
        
        stage_state = self.state.stage_states[stage_id]
        current_state = stage_state.state
        
        # Apply transition
        if event == 'start':
            stage_state.state = StageState.RUNNING
            stage_state.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            logger.info(f"Stage '{stage_id}' started at {stage_state.started_at}")
            
        elif event == 'complete':
            stage_state.state = StageState.COMPLETE
            stage_state.completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            logger.info(f"Stage '{stage_id}' completed at {stage_state.completed_at}")
            
            # Move to next stage per pipeline config
            stage_config = self.pipeline.get_stage_by_id(stage_id)
            if stage_config:
                next_stage_id = stage_config.on_success
                if next_stage_id == 'complete':
                    self.state.pipeline_status = PipelineStatus.SUCCEEDED
                    logger.info(f"Pipeline completed successfully")
                elif next_stage_id in self.state.stage_states:
                    self.state.current_stage_id = next_stage_id
                    logger.info(f"Next stage: '{next_stage_id}'")
                    
        elif event == 'fail':
            stage_state.state = StageState.FAILED
            logger.info(f"Stage '{stage_id}' failed")
            
            # Apply retry policy from pipeline config
            stage_config = self.pipeline.get_stage_by_id(stage_id)
            if stage_config and isinstance(stage_config.on_failure, dict):
                if 'retry' in stage_config.on_failure:
                    max_retries = stage_config.on_failure['retry']
                    if stage_state.retry_count < max_retries:
                        stage_state.retry_count += 1
                        stage_state.state = StageState.PENDING
                        logger.info(f"Retrying stage '{stage_id}' (attempt {stage_state.retry_count}/{max_retries})")
                    else:
                        then_action = stage_config.on_failure.get('then', 'fail')
                        if then_action == 'escalate':
                            stage_state.state = StageState.ESCALATED
                            logger.info(f"Stage '{stage_id}' escalated after {max_retries} retries")
                        else:
                            stage_state.state = StageState.CRASHED_UNRECOVERABLE
                            logger.info(f"Stage '{stage_id}' marked unrecoverable after {max_retries} retries")
                            
        elif event == 'crash':
            stage_state.state = StageState.CRASHED_RECOVERABLE
            logger.info(f"Stage '{stage_id}' crashed, marked as recoverable")
            
        elif event == 'retry':
            stage_state.state = StageState.PENDING
            logger.info(f"Stage '{stage_id}' retrying")
            
        elif event == 'escalate':
            stage_state.state = StageState.ESCALATED
            logger.info(f"Stage '{stage_id}' escalated")
            
        elif event == 'unrecoverable':
            stage_state.state = StageState.CRASHED_UNRECOVERABLE
            logger.info(f"Stage '{stage_id}' marked unrecoverable")
            
        elif event == 'bounce':
            stage_state.state = StageState.REJECTED
            logger.info(f"Stage '{stage_id}' rejected")
            
        # Update last_updated_at
        self.state.last_updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        return self.state


def atomic_write_state(path: Path, state: Any) -> None:
    """
    Atomically write workflow state to disk. Crash-safe on POSIX.
    
    Args:
        path: Path to the workflow-state.json file
        state: WorkflowState object or dict to write
    """
    logger.info(f"Writing workflow state atomically to: {path}")
    
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to JSON if it's a Pydantic model
    if hasattr(state, 'model_dump_json'):
        state_json = state.model_dump_json(indent=2)
    elif hasattr(state, 'model_dump'):
        state_json = json.dumps(state.model_dump(), indent=2)
    else:
        state_json = json.dumps(state, indent=2)
    
    # Create temporary file in same directory for atomic rename
    fd, tmppath = tempfile.mkstemp(dir=path.parent, prefix=".wf-", suffix=".tmp")
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(state_json)
            f.flush()
            os.fsync(f.fileno())  # Persist file contents
        
        os.replace(tmppath, path)  # Atomic rename
        
        # Persist directory entry (skip on Windows due to permission issues)
        if sys.platform != 'win32':
            try:
                dirfd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)
            except (PermissionError, OSError):
                logger.warning("Failed to fsync directory (non-critical on Windows)")
            
        logger.debug(f"Successfully wrote workflow state to: {path}")
        
    except BaseException:
        try:
            os.unlink(tmppath)
        except FileNotFoundError:
            pass
        logger.error(f"Failed to write workflow state atomically", exc_info=True)
        raise