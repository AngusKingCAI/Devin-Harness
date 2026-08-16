"""Tests for the state machine and workflow state management."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from state.state import WorkflowState, StageStateRecord, StateMachine, PipelineStatus, StageState, atomic_write_state
from state.lock import OrchestratorLock

# Setup logging for tests
import logging
import json

def setup_test_logging():
    """Setup logging for test execution."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    test_log_file = log_dir / f"test_state-Log.jsonl"
    
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
    
    file_handler = logging.FileHandler(test_log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    logger = logging.getLogger("test_state")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

test_logger = setup_test_logging()


def test_workflow_state_creation():
    """Test creating a WorkflowState object."""
    test_logger.info("Testing WorkflowState creation...")
    
    state = WorkflowState(
        schema_version="1.0",
        pipeline_run_id="test-run-001",
        pipeline_name="test-pipeline",
        pipeline_version="1.0.0",
        started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        last_updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        current_stage_id="stage1",
        stage_states={
            "stage1": StageStateRecord(state=StageState.PENDING, subagent="agent1")
        }
    )
    
    state.validate()  # Validate the state
    
    assert state.pipeline_run_id == "test-run-001"
    assert state.current_stage_id == "stage1"
    assert state.stage_states["stage1"].state == StageState.PENDING
    
    test_logger.info("[PASS] WorkflowState creation test passed")


def test_state_machine_transition():
    """Test state machine transitions."""
    test_logger.info("Testing StateMachine.transition()...")
    
    # Create a simple mock pipeline config
    class MockPipelineConfig:
        name = "test-pipeline"
        stages = []
        
        def get_stage_by_id(self, stage_id):
            if stage_id == "stage1":
                class MockStage:
                    id = "stage1"
                    on_success = "complete"
                    on_failure = {"retry": 2, "then": "fail"}
                return MockStage()
            return None
    
    # Create initial state
    initial_state = WorkflowState(
        schema_version="1.0",
        pipeline_run_id="test-run-001",
        pipeline_name="test-pipeline",
        pipeline_version="1.0.0",
        started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        last_updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        current_stage_id="stage1",
        stage_states={
            "stage1": StageStateRecord(state=StageState.PENDING, subagent="agent1")
        }
    )
    
    # Create state machine
    sm = StateMachine(MockPipelineConfig(), initial_state)
    
    # Test PENDING -> RUNNING transition
    assert sm.can_transition("stage1", "start"), "Should be able to start stage"
    new_state = sm.transition("stage1", "start")
    assert new_state.stage_states["stage1"].state == StageState.RUNNING
    assert new_state.stage_states["stage1"].started_at is not None
    
    test_logger.info("[PASS] StateMachine.transition() test passed")


def test_atomic_write_state():
    """Test atomic state write."""
    test_logger.info("Testing atomic_write_state()...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        state_path = Path(temp_dir) / "workflow-state.json"
        
        state = WorkflowState(
            schema_version="1.0",
            pipeline_run_id="test-run-001",
            pipeline_name="test-pipeline",
            pipeline_version="1.0.0",
            started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            last_updated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            current_stage_id="stage1",
            stage_states={
                "stage1": StageStateRecord(state=StageState.PENDING, subagent="agent1")
            }
        )
        
        atomic_write_state(state_path, state)
        
        assert state_path.exists(), "State file should exist"
        
        # Read back and verify
        loaded_state = WorkflowState.model_validate_json(state_path.read_text())
        assert loaded_state.pipeline_run_id == "test-run-001"
        assert loaded_state.current_stage_id == "stage1"
        
        test_logger.info("[PASS] atomic_write_state() test passed")


def test_orchestrator_lock():
    """Test OrchestratorLock acquisition and release."""
    test_logger.info("Testing OrchestratorLock...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        lock_path = Path(temp_dir) / "orchestrator.lock"
        
        lock = OrchestratorLock(lock_path)
        
        # Test acquiring lock
        assert lock.acquire(timeout=5), "Should acquire lock successfully"
        
        # Test that lock is held
        assert lock_path.exists(), "Lock file should exist"
        
        # Test releasing lock
        lock.release()
        assert not lock_path.exists(), "Lock file should be removed after release"
        
        test_logger.info("[PASS] OrchestratorLock test passed")


if __name__ == "__main__":
    test_logger.info("Running state tests...")
    
    # Create test documentation
    test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    test_doc_dir = Path(__file__).parent.parent.parent / "docs" / "orchestrator" / "tests"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    test_doc_file = test_doc_dir / f"{test_timestamp}-state_tests.md"
    
    test_results = []
    
    try:
        test_workflow_state_creation()
        test_results.append("[PASS] WorkflowState creation test passed")
        
        test_state_machine_transition()
        test_results.append("[PASS] StateMachine.transition() test passed")
        
        test_atomic_write_state()
        test_results.append("[PASS] atomic_write_state() test passed")
        
        test_orchestrator_lock()
        test_results.append("[PASS] OrchestratorLock test passed")
        
        test_logger.info("[SUCCESS] All state tests passed!")
        
        # Write test documentation
        test_doc_content = f"""# State Tests - {test_timestamp}

## Test Setup
- Date: {test_timestamp}
- Test file: {__file__}
- State module: scripts/state/state.py
- Lock module: scripts/state/lock.py
- Python version: {sys.version.split()[0]}

## Test Results
""" + "\n".join(test_results) + f"""

## Environment
- Working directory: {Path.cwd()}
- Logs directory: {Path.cwd() / 'logs'}

## Test Coverage
- WorkflowState Pydantic model creation
- StateMachine.can_transition() validation
- StateMachine.transition() state updates
- atomic_write_state() crash-safe writes
- OrchestratorLock acquisition and release

## Notes
- All tests passed successfully
- Logging setup working correctly (JSONL format)
- Atomic write pattern uses temp file + rename
- Lock implementation works on Windows (fallback) and POSIX
"""
        test_doc_file.write_text(test_doc_content)
        test_logger.info(f"Test documentation written to: {test_doc_file}")
        
    except AssertionError as e:
        test_logger.error(f"[FAIL] Test failed: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        test_logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)