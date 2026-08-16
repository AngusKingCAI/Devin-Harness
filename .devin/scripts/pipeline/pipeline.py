"""Pipeline configuration loader and validation."""

import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
import jsonschema

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


class StageInput(BaseModel):
    """Input configuration for a pipeline stage."""
    task_prompt_file: str
    from_stage_outputs: Optional[list[str]] = None


class StageConfig(BaseModel):
    """Configuration for a single pipeline stage."""
    id: str
    subagent: str
    input: StageInput
    on_success: Union[str, Dict[str, Any]]
    on_failure: Union[str, Dict[str, Any]]
    on_reject: Optional[Dict[str, Any]] = None


class TerminalState(BaseModel):
    """Terminal state configuration."""
    status: str
    notify: Optional[str] = None


class PipelineConfig(BaseModel):
    """Pipeline configuration loaded from pipeline.json."""
    name: str
    version: str
    stages: list[StageConfig]
    terminal_states: Dict[str, TerminalState]
    
    @classmethod
    def load(cls, config_path: Path) -> "PipelineConfig":
        """
        Load and validate pipeline configuration from a JSON file.
        
        Args:
            config_path: Path to the pipeline.json file
            
        Returns:
            PipelineConfig object
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        logger.info(f"Loading pipeline configuration from: {config_path}")
        
        if not config_path.exists():
            logger.error(f"Pipeline configuration file not found: {config_path}")
            raise FileNotFoundError(f"Pipeline configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            logger.debug(f"Loaded pipeline data: {config_data}")
            
            # Validate against JSON schema
            cls._validate_schema(config_data)
            
            # Parse configuration
            config = cls(**config_data)
            
            logger.info(f"Loaded pipeline '{config.name}' version {config.version} with {len(config.stages)} stages")
            logger.debug(f"Stages: {[stage.id for stage in config.stages]}")
            
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse pipeline JSON: {e}", exc_info=True)
            raise ValueError(f"Invalid JSON in pipeline configuration: {e}")
        except Exception as e:
            logger.error(f"Failed to load pipeline configuration: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _validate_schema(config_data: Dict[str, Any]) -> None:
        """
        Validate pipeline configuration against JSON schema.
        
        Args:
            config_data: Parsed configuration dictionary
            
        Raises:
            ValueError: If configuration doesn't match schema
        """
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["name", "version", "stages", "terminal_states"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "stages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "subagent", "input", "on_success", "on_failure"],
                        "properties": {
                            "id": {"type": "string"},
                            "subagent": {"type": "string"},
                            "input": {
                                "type": "object",
                                "required": ["task_prompt_file"],
                                "properties": {
                                    "task_prompt_file": {"type": "string"},
                                    "from_stage_outputs": {"type": "array", "items": {"type": "string"}}
                                }
                            },
                            "on_success": {"type": ["string", "object"]},
                            "on_failure": {"type": ["string", "object"]},
                            "on_reject": {"type": "object"}
                        }
                    }
                },
                "terminal_states": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {
                            "type": "object",
                            "required": ["status"],
                            "properties": {
                                "status": {"type": "string"},
                                "notify": {"type": "string"}
                            }
                        }
                    }
                }
            }
        }
        
        try:
            jsonschema.validate(instance=config_data, schema=schema)
            logger.debug("Pipeline configuration schema validation passed")
        except jsonschema.ValidationError as e:
            logger.error(f"Pipeline configuration schema validation failed: {e}")
            raise ValueError(f"Pipeline configuration schema validation failed: {e}")
    
    def get_stage_by_id(self, stage_id: str) -> Optional[StageConfig]:
        """Get a stage configuration by its ID."""
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        return None
    
    def get_terminal_state(self, state_name: str) -> Optional[TerminalState]:
        """Get a terminal state configuration by its name."""
        return self.terminal_states.get(state_name)