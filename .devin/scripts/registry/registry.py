"""Registry module for managing sub-agent profiles."""

import logging
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

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


class ContractRef(BaseModel):
    """Reference to a JSON schema contract."""
    type: str = "object"
    schema_ref: Optional[str] = None
    required: Optional[list[str]] = None
    schema_definition: Optional[Dict[str, Any]] = None


class RetryPolicy(BaseModel):
    """Retry policy configuration."""
    transient: Dict[str, Any] = {"max_attempts": 3, "backoff": "exponential"}
    logic_error: Dict[str, Any] = {"max_attempts": 1, "escalate": "human"}
    environment_error: Dict[str, Any] = {"max_attempts": 5, "backoff": "linear"}


class RegistryEntry(BaseModel):
    """Represents a registered sub-agent profile."""
    name: str
    description: str
    profile_path: Path
    allowed_tools: Optional[list[str]] = None
    max_nesting: int = 0
    input_contract: Optional[ContractRef] = None
    output_contract: Optional[ContractRef] = None
    timeout_seconds: int = 3600
    retry_policy: RetryPolicy = RetryPolicy()
    idempotency_key_template: Optional[str] = None
    max_concurrent_instances: int = 1
    human_approval_required: bool = False
    # NOTE: no 'model' field — all sub-agents run on SWE-1.6 (Section 11.14)


class Registry(BaseModel):
    """Registry of sub-agent profiles."""
    entries: Dict[str, RegistryEntry] = {}

    @classmethod
    def load(cls, project_agents_dir: Path, user_agents_dir: Path) -> "Registry":
        """
        Load registry from agent directories.
        
        Args:
            project_agents_dir: Path to project-scoped agents directory
            user_agents_dir: Path to user-scoped agents directory
            
        Returns:
            Registry with loaded entries
        """
        logger.info(f"Loading registry from project_agents_dir={project_agents_dir}, user_agents_dir={user_agents_dir}")
        entries = {}
        
        # Load project-scoped agents first
        if project_agents_dir.exists():
            logger.debug(f"Scanning project agents directory: {project_agents_dir}")
            for md_file in project_agents_dir.glob("*.md"):
                logger.debug(f"Found agent file: {md_file}")
                entry = cls._load_profile(md_file)
                if entry:
                    entries[entry.name] = entry
                    logger.info(f"Loaded agent: {entry.name} from {md_file}")
            
            # Check for directory layout (<name>/AGENT.md)
            for agent_dir in project_agents_dir.iterdir():
                if agent_dir.is_dir():
                    logger.debug(f"Found agent directory: {agent_dir}")
                    for filename in ["AGENT.md", "AGENTS.md", "agent.md", "agents.md"]:
                        md_file = agent_dir / filename
                        if md_file.exists():
                            logger.debug(f"Found agent file in directory: {md_file}")
                            entry = cls._load_profile(md_file)
                            if entry:
                                entries[entry.name] = entry
                                logger.info(f"Loaded agent: {entry.name} from {md_file}")
                            break
        
        # Load user-scoped agents (override project-scoped on name collision)
        if user_agents_dir.exists():
            logger.debug(f"Scanning user agents directory: {user_agents_dir}")
            for md_file in user_agents_dir.glob("*.md"):
                logger.debug(f"Found user agent file: {md_file}")
                entry = cls._load_profile(md_file)
                if entry:
                    entries[entry.name] = entry
                    logger.info(f"Loaded user agent (overrides): {entry.name} from {md_file}")
            
            # Check for directory layout
            for agent_dir in user_agents_dir.iterdir():
                if agent_dir.is_dir():
                    logger.debug(f"Found user agent directory: {agent_dir}")
                    for filename in ["AGENT.md", "AGENTS.md", "agent.md", "agents.md"]:
                        md_file = agent_dir / filename
                        if md_file.exists():
                            logger.debug(f"Found user agent file in directory: {md_file}")
                            entry = cls._load_profile(md_file)
                            if entry:
                                entries[entry.name] = entry
                                logger.info(f"Loaded user agent (overrides): {entry.name} from {md_file}")
                            break
        
        logger.info(f"Registry loaded successfully with {len(entries)} entries: {list(entries.keys())}")
        return cls(entries=entries)

    @classmethod
    def _load_profile(cls, profile_path: Path) -> Optional[RegistryEntry]:
        """
        Load a single sub-agent profile from a markdown file.
        
        Args:
            profile_path: Path to the markdown profile file
            
        Returns:
            RegistryEntry or None if loading fails
        """
        logger.debug(f"Loading profile from: {profile_path}")
        try:
            frontmatter, body = cls._parse_frontmatter(profile_path)
            
            # Extract fields from frontmatter
            name = frontmatter.get("name", profile_path.stem)
            description = frontmatter.get("description", "")
            allowed_tools = frontmatter.get("allowed-tools")
            max_nesting = frontmatter.get("max-nesting", 0)
            
            # Extract orchestrator-specific fields
            orchestrator_config = frontmatter.get("orchestrator", {})
            input_contract = orchestrator_config.get("input_contract")
            output_contract = orchestrator_config.get("output_contract")
            timeout_seconds = orchestrator_config.get("timeout_seconds", 3600)
            retry_policy_config = orchestrator_config.get("retry_policy", {})
            idempotency_key_template = orchestrator_config.get("idempotency_key")
            max_concurrent_instances = orchestrator_config.get("max_concurrent_instances", 1)
            human_approval_required = orchestrator_config.get("human_approval_required", False)
            
            # Handle schema vs schema_definition naming
            if input_contract and "schema" in input_contract:
                input_contract["schema_definition"] = input_contract.pop("schema")
            if output_contract and "schema" in output_contract:
                output_contract["schema_definition"] = output_contract.pop("schema")
            
            # Build objects
            input_contract_obj = ContractRef(**input_contract) if input_contract else None
            output_contract_obj = ContractRef(**output_contract) if output_contract else None
            retry_policy_obj = RetryPolicy(**retry_policy_config) if retry_policy_config else RetryPolicy()
            
            return RegistryEntry(
                name=name,
                description=description,
                profile_path=profile_path,
                allowed_tools=allowed_tools,
                max_nesting=max_nesting,
                input_contract=input_contract_obj,
                output_contract=output_contract_obj,
                timeout_seconds=timeout_seconds,
                retry_policy=retry_policy_obj,
                idempotency_key_template=idempotency_key_template,
                max_concurrent_instances=max_concurrent_instances,
                human_approval_required=human_approval_required
            )
        except Exception as e:
            logger.error(f"Failed to load profile {profile_path}: {e}", exc_info=True)
            return None

    @classmethod
    def _parse_frontmatter(cls, path: Path) -> tuple[Dict[str, Any], str]:
        """
        Parse YAML frontmatter from a markdown file.
        
        Args:
            path: Path to the markdown file
            
        Returns:
            Tuple of (frontmatter_dict, markdown_body)
        """
        logger.debug(f"Parsing frontmatter from: {path}")
        content = path.read_text(encoding="utf-8")
        
        # Split on --- boundaries
        parts = content.split("---")
        
        if len(parts) >= 3:
            # Format: ---\nYAML\n---\nmarkdown
            frontmatter_str = parts[1].strip()
            markdown_body = "---".join(parts[2:]).strip()
            
            try:
                frontmatter = yaml.safe_load(frontmatter_str)
                if frontmatter is None:
                    frontmatter = {}
                logger.debug(f"Successfully parsed frontmatter with {len(frontmatter)} fields")
                return frontmatter, markdown_body
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML in {path}: {e}")
                return {}, content
        
        # No valid frontmatter found
        logger.debug(f"No valid frontmatter found in {path}")
        return {}, content