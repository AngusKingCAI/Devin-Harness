# Testing Best Practices

## Test Organization

### Directory Structure
- Write tests in `tests/[domain]/` directory structure
- Mirror the scripts domain structure in tests
- Example: `tests/registry/test_registry.py` for `scripts/registry/registry.py`

## Testing Patterns

### File Operation Testing
- Use temporary files/directories for testing file operations
- Clean up temporary files in finally blocks
- Test both success and failure paths
- Verify edge cases and error handling

### Module Testing
- Import modules using `sys.path` manipulation for local testing
- Add scripts directory to path: `sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))`
- Test individual functions in isolation
- Test integration between components

### Test Coverage
- Test both success and failure paths
- Verify edge cases and error handling
- Ensure all public functions have tests
- Test data validation and schema parsing

## Windows-Specific Testing

### Unicode Encoding
- Handle Windows Unicode encoding issues
- Avoid special Unicode characters in test output
- Use ASCII-safe characters for test messages
- Test on Windows environment to catch platform-specific issues

### Path Handling
- Test with both forward slashes and backslashes
- Use `pathlib.Path` for cross-platform compatibility
- Test temporary file creation and cleanup

## Test Execution

### Running Tests
- Run tests before proceeding to next component
- Fix test failures before moving forward
- Ensure all tests pass before considering component complete
- Run tests from appropriate directory

### Test Maintenance
- Update tests when implementation changes
- Keep tests simple and focused
- Remove obsolete tests
- Document test purpose in docstrings

## Example Test Structure

```python
"""Tests for the registry module."""

import sys
import tempfile
from pathlib import Path

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from registry.registry import Registry, RegistryEntry

def test_function_name():
    """Test description."""
    # Setup
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        # Test
        result = function_to_test(temp_path)
        assert result == expected, f"Expected {expected}, got {result}"
        print("[PASS] Test passed")
    finally:
        # Cleanup
        temp_path.unlink()

if __name__ == "__main__":
    # Run tests
    test_function_name()
    print("[SUCCESS] All tests passed!")
```

## Continuous Testing

- Write unit tests immediately after implementing each function
- Run tests before proceeding to the next component
- Fix any test failures before moving forward
- Ensure all tests pass before considering a component complete