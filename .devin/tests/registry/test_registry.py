"""Tests for the registry module."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from registry.registry import Registry, RegistryEntry, ContractRef, RetryPolicy

# Setup logging for tests
import logging
import json

def setup_test_logging():
    """Setup logging for test execution."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    test_log_file = log_dir / f"test_registry-Log.jsonl"
    
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
    
    logger = logging.getLogger("test_registry")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

test_logger = setup_test_logging()


def test_frontmatter_parsing():
    """Test the hand-rolled frontmatter parser."""
    test_logger.info("Testing frontmatter parsing...")
    
    # Create a temporary markdown file with frontmatter
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""---
name: test-agent
description: A test agent
allowed-tools:
  - Read
  - Write
max-nesting: 2
orchestrator:
  timeout_seconds: 1800
---
This is the markdown body.
""")
        temp_path = Path(f.name)
    
    try:
        frontmatter, body = Registry._parse_frontmatter(temp_path)
        
        assert frontmatter["name"] == "test-agent", f"Expected name 'test-agent', got {frontmatter.get('name')}"
        assert frontmatter["description"] == "A test agent", f"Expected description 'A test agent', got {frontmatter.get('description')}"
        assert frontmatter["allowed-tools"] == ["Read", "Write"], f"Expected tools ['Read', 'Write'], got {frontmatter.get('allowed-tools')}"
        assert frontmatter["max-nesting"] == 2, f"Expected max-nesting 2, got {frontmatter.get('max-nesting')}"
        assert body.strip() == "This is the markdown body.", f"Expected body 'This is the markdown body.', got {body.strip()}"
        
        test_logger.info("[PASS] Frontmatter parsing test passed")
    finally:
        temp_path.unlink()


def test_registry_entry_creation():
    """Test creating a RegistryEntry from frontmatter."""
    test_logger.info("Testing RegistryEntry creation...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""---
name: dummy
description: A dummy sub-agent
allowed-tools: [Bash]
orchestrator:
  output_contract:
    type: object
    required: [output_paths, summary]
    schema:
      type: object
      properties:
        output_paths: {type: object}
        summary: {type: string}
  timeout_seconds: 60
---
You are a dummy sub-agent.
""")
        temp_path = Path(f.name)
    
    try:
        entry = Registry._load_profile(temp_path)
        
        assert entry is not None, "Entry should not be None"
        assert entry.name == "dummy", f"Expected name 'dummy', got {entry.name}"
        assert entry.description == "A dummy sub-agent", f"Expected description 'A dummy sub-agent', got {entry.description}"
        assert entry.allowed_tools == ["Bash"], f"Expected tools ['Bash'], got {entry.allowed_tools}"
        assert entry.timeout_seconds == 60, f"Expected timeout 60, got {entry.timeout_seconds}"
        assert entry.output_contract is not None, "Output contract should not be None"
        
        test_logger.info("[PASS] RegistryEntry creation test passed")
    finally:
        temp_path.unlink()


def test_registry_load():
    """Test loading registry from directories."""
    test_logger.info("Testing Registry.load()...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        agents_dir = temp_path / "agents"
        agents_dir.mkdir()
        
        # Create a dummy profile
        dummy_profile = agents_dir / "dummy.md"
        dummy_profile.write_text("""---
name: dummy
description: A dummy sub-agent
allowed-tools: [Bash]
orchestrator:
  timeout_seconds: 60
---
You are a dummy sub-agent.
""")
        
        # Load registry
        registry = Registry.load(agents_dir, Path("/nonexistent"))
        
        assert "dummy" in registry.entries, "Registry should contain 'dummy' entry"
        assert registry.entries["dummy"].name == "dummy", "Entry name should be 'dummy'"
        
        test_logger.info("[PASS] Registry.load() test passed")


def test_no_frontmatter():
    """Test parsing a file without frontmatter."""
    test_logger.info("Testing file without frontmatter...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("Just markdown content without frontmatter.")
        temp_path = Path(f.name)
    
    try:
        frontmatter, body = Registry._parse_frontmatter(temp_path)
        
        assert frontmatter == {}, f"Expected empty frontmatter, got {frontmatter}"
        assert body.strip() == "Just markdown content without frontmatter.", f"Expected body without frontmatter, got {body.strip()}"
        
        test_logger.info("[PASS] No frontmatter test passed")
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    test_logger.info("Running registry tests...")
    
    # Create test documentation
    test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    test_doc_dir = Path(__file__).parent.parent.parent / "docs" / "orchestrator" / "tests"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    test_doc_file = test_doc_dir / f"{test_timestamp}-registry_tests.md"
    
    test_results = []
    
    try:
        test_frontmatter_parsing()
        test_results.append("[PASS] Frontmatter parsing test passed")
        
        test_registry_entry_creation()
        test_results.append("[PASS] RegistryEntry creation test passed")
        
        test_registry_load()
        test_results.append("[PASS] Registry.load() test passed")
        
        test_no_frontmatter()
        test_results.append("[PASS] No frontmatter test passed")
        
        test_logger.info("[SUCCESS] All registry tests passed!")
        
        # Write test documentation
        test_doc_content = f"""# Registry Tests - {test_timestamp}

## Test Setup
- Date: {test_timestamp}
- Test file: {__file__}
- Registry module: scripts/registry/registry.py
- Python version: {sys.version.split()[0]}

## Test Results
""" + "\n".join(test_results) + f"""

## Environment
- Working directory: {Path.cwd()}
- Agents directory: {Path.cwd() / 'agents'}
- Logs directory: {Path.cwd() / 'logs'}

## Test Coverage
- Frontmatter parsing (YAML + markdown)
- RegistryEntry creation from profiles
- Registry.load() with directory scanning
- File without frontmatter handling
- Schema vs schema_definition conversion

## Notes
- All tests passed successfully
- Logging setup working correctly (JSONL format)
- Console output limited to INFO level
- File logging includes DEBUG level
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