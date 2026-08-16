"""Tests for the pipeline configuration loader."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from pipeline.pipeline import PipelineConfig, StageConfig, StageInput, TerminalState

# Setup logging for tests
import logging
import json

def setup_test_logging():
    """Setup logging for test execution."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    test_log_file = log_dir / f"test_pipeline-Log.jsonl"
    
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
    
    logger = logging.getLogger("test_pipeline")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

test_logger = setup_test_logging()


def test_pipeline_load():
    """Test loading pipeline configuration from JSON file."""
    test_logger.info("Testing PipelineConfig.load()...")
    
    # Create a temporary pipeline.json file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("""{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "name": "test-pipeline",
  "version": "1.0.0",
  "stages": [
    {
      "id": "test-stage",
      "subagent": "dummy",
      "input": {
        "task_prompt_file": "tasks/test-task.md"
      },
      "on_success": "complete",
      "on_failure": "fail"
    }
  ],
  "terminal_states": {
    "complete": {"status": "succeeded"},
    "fail": {"status": "failed"}
  }
}""")
        temp_path = Path(f.name)
    
    try:
        config = PipelineConfig.load(temp_path)
        
        assert config.name == "test-pipeline", f"Expected name 'test-pipeline', got {config.name}"
        assert config.version == "1.0.0", f"Expected version '1.0.0', got {config.version}"
        assert len(config.stages) == 1, f"Expected 1 stage, got {len(config.stages)}"
        assert config.stages[0].id == "test-stage", f"Expected stage id 'test-stage', got {config.stages[0].id}"
        assert config.stages[0].subagent == "dummy", f"Expected subagent 'dummy', got {config.stages[0].subagent}"
        
        test_logger.info("[PASS] PipelineConfig.load() test passed")
    finally:
        temp_path.unlink()


def test_get_stage_by_id():
    """Test retrieving a stage by its ID."""
    test_logger.info("Testing get_stage_by_id()...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("""{
  "name": "test-pipeline",
  "version": "1.0.0",
  "stages": [
    {"id": "stage1", "subagent": "agent1", "input": {"task_prompt_file": "task1.md"}, "on_success": "stage2", "on_failure": "fail"},
    {"id": "stage2", "subagent": "agent2", "input": {"task_prompt_file": "task2.md"}, "on_success": "complete", "on_failure": "fail"}
  ],
  "terminal_states": {"complete": {"status": "succeeded"}, "fail": {"status": "failed"}}
}""")
        temp_path = Path(f.name)
    
    try:
        config = PipelineConfig.load(temp_path)
        
        stage1 = config.get_stage_by_id("stage1")
        assert stage1 is not None, "Stage1 should exist"
        assert stage1.subagent == "agent1", f"Expected subagent 'agent1', got {stage1.subagent}"
        
        stage2 = config.get_stage_by_id("stage2")
        assert stage2 is not None, "Stage2 should exist"
        assert stage2.subagent == "agent2", f"Expected subagent 'agent2', got {stage2.subagent}"
        
        nonexistent = config.get_stage_by_id("nonexistent")
        assert nonexistent is None, "Nonexistent stage should return None"
        
        test_logger.info("[PASS] get_stage_by_id() test passed")
    finally:
        temp_path.unlink()


def test_schema_validation():
    """Test JSON schema validation."""
    test_logger.info("Testing schema validation...")
    
    # Test invalid schema (missing required field)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("""{
  "name": "test-pipeline",
  "version": "1.0.0",
  "stages": []
}""")
        temp_path = Path(f.name)
    
    try:
        try:
            config = PipelineConfig.load(temp_path)
            test_logger.error("[FAIL] Schema validation should have failed for missing terminal_states")
            sys.exit(1)
        except ValueError as e:
            test_logger.info(f"[PASS] Schema validation correctly failed: {e}")
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    test_logger.info("Running pipeline tests...")
    
    # Create test documentation
    test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    test_doc_dir = Path(__file__).parent.parent.parent / "docs" / "orchestrator" / "tests"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    test_doc_file = test_doc_dir / f"{test_timestamp}-pipeline_tests.md"
    
    test_results = []
    
    try:
        test_pipeline_load()
        test_results.append("[PASS] PipelineConfig.load() test passed")
        
        test_get_stage_by_id()
        test_results.append("[PASS] get_stage_by_id() test passed")
        
        test_schema_validation()
        test_results.append("[PASS] Schema validation test passed")
        
        test_logger.info("[SUCCESS] All pipeline tests passed!")
        
        # Write test documentation
        test_doc_content = f"""# Pipeline Tests - {test_timestamp}

## Test Setup
- Date: {test_timestamp}
- Test file: {__file__}
- Pipeline module: scripts/pipeline/pipeline.py
- Python version: {sys.version.split()[0]}

## Test Results
""" + "\n".join(test_results) + f"""

## Environment
- Working directory: {Path.cwd()}
- Config directory: {Path.cwd() / 'config' / 'pipeline'}

## Test Coverage
- PipelineConfig.load() from JSON file
- Schema validation against JSON Schema
- get_stage_by_id() for stage lookup
- Terminal state configuration

## Notes
- All tests passed successfully
- Logging setup working correctly (JSONL format)
- JSON schema validation using jsonschema library
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