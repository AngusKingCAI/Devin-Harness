# Logging Setup Template

This file contains the standard logging setup code that should be included at the top of every Python file in the Orchestrator project.

## Standard Logging Template

Add this code to the top of every Python file (after imports):

```python
import logging
import json
from pathlib import Path
from datetime import datetime, timezone

# Setup logging for this module
def setup_logging(module_name: str):
    """Setup JSONL logging for a module."""
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create log file path: logs/{module_name}-Log.jsonl
    log_file = log_dir / f"{module_name}-Log.jsonl"
    
    # Create custom JSON formatter
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
            
            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            
            # Add extra fields if present
            if hasattr(record, 'extra_fields'):
                log_entry.update(record.extra_fields)
            
            return json.dumps(log_entry)
    
    # Setup file handler
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_handler.setFormatter(JsonFormatter())
    
    # Setup console handler (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Only INFO and above to console
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Configure logger
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)  # Capture all levels
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger for this module
logger = setup_logging(__name__)
```

## Usage Examples

### Basic Usage

```python
# At the top of your file after imports
logger = setup_logging(__name__)

# In your functions
def my_function():
    logger.info("Starting my_function")
    try:
        # Do work
        logger.debug("Processing data")
        logger.info("Function completed successfully")
    except Exception as e:
        logger.error(f"Function failed: {e}", exc_info=True)
        raise
```

### With Extra Fields

```python
# Add extra context to log entries
def process_data(data_id: str):
    logger.info(f"Processing data {data_id}", extra={'extra_fields': {'data_id': data_id}})
```

### Different Log Levels

```python
logger.debug("Detailed diagnostic information")
logger.info("Normal operational events")
logger.warning("Something unexpected but recoverable")
logger.error("Operation failed")
logger.critical("Severe failure preventing continuation")
```

## Log File Structure

Logs will be organized as:
```
.devin/logs/
├── registry.registry-Log.jsonl
├── pipeline.pipeline-Log.jsonl
├── state.state-Log.jsonl
├── memory.memory-Log.jsonl
└── orchestrator.main-Log.jsonl
```

**Naming Convention:**
- Log files use the full Python module path from `__name__`
- `scripts/registry/registry.py` → `registry.registry-Log.jsonl`
- This provides full context and avoids naming conflicts
- Follows standard Python module naming conventions

Each log file contains JSONL entries (one JSON object per line) for easy parsing and analysis.

## Test Documentation

Test runs should create documentation in:
```
.devin/docs/orchestrator/tests/{YYYY-MM-DD_HH-MM-SS}-{TestName}.md
```

Include test setup, execution, results, and any issues encountered.

## Logging Lessons Learned

### Timezone Handling
- Use `datetime.now(timezone.utc)` instead of `datetime.utcnow()` (deprecated in Python 3.12+)
- Format timestamp with `.replace("+00:00", "Z")` for proper UTC "Z" suffix
- Import `timezone` from datetime module

### Windows-Specific Considerations
- Avoid Unicode characters in log messages (causes encoding issues on Windows)
- Use ASCII-safe characters like `[PASS]`, `[FAIL]`, `[SUCCESS]` instead of special Unicode
- File encoding must be specified as `utf-8` for cross-platform compatibility

### Log Level Strategy
- DEBUG: Detailed diagnostic information (file only)
- INFO: Normal operational events (file + console)
- WARNING: Unexpected but recoverable (file + console)
- ERROR: Operation failures (file + console)
- CRITICAL: Severe failures (file + console)

### JSONL Format Benefits
- Structured logging for easy parsing and analysis
- One JSON object per line for append-friendly format
- Machine-parsable for log analysis tools
- Human-readable when pretty-printed if needed