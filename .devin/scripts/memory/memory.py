"""Memory system facade combining audit log and decision database."""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

from memory.audit import append_audit, verify_audit_chain
from memory.decisions import (
    verify_fts5, initialize_schema, insert_decision, search_decisions,
    insert_shared_fact, search_shared_facts
)

# Setup logging for this module
def setup_logging(module_name: str):
    """Setup JSONL logging for a module."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"{module_name}-Log.jsonl"
    
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat().replace("+00:00", "Z"),
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
            
            return __import__('json').dumps(log_entry)
    
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
    
    logger_instance = logging.getLogger(module_name)
    logger_instance.setLevel(logging.DEBUG)
    logger_instance.addHandler(file_handler)
    logger_instance.addHandler(console_handler)
    
    return logger_instance

logger = setup_logging(__name__)


class MemorySystem:
    """Facade for the memory system combining audit log and decision database."""
    
    def __init__(self, db_path: Path, audit_log_path: Path):
        """
        Initialize the memory system.
        
        Args:
            db_path: Path to decisions.sqlite
            audit_log_path: Path to action-log.jsonl
        """
        self.db_path = db_path
        self.audit_log_path = audit_log_path
        self.conn = None
        self.current_hash = "genesis"
        
        logger.info(f"Initializing memory system with DB: {db_path}, Audit: {audit_log_path}")
    
    def initialize(self) -> None:
        """Initialize the memory system (database schema and verify FTS5)."""
        logger.info("Initializing memory system...")
        
        # Create database directory
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        self.conn = sqlite3.connect(self.db_path)
        
        # Verify FTS5 availability
        verify_fts5(self.conn)
        
        # Initialize schema
        initialize_schema(self.conn)
        
        # Verify WAL mode
        cursor = self.conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        logger.info(f"Database journal mode: {journal_mode}")
        
        if journal_mode != "wal":
            logger.warning(f"Expected WAL mode, got: {journal_mode}")
        
        logger.info("Memory system initialized successfully")
    
    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Memory system closed")
    
    def audit_event(self, payload: Dict[str, Any]) -> str:
        """
        Append an event to the audit log.
        
        Args:
            payload: Event payload
            
        Returns:
            The hash of the appended record
        """
        self.current_hash = append_audit(self.audit_log_path, payload, self.current_hash)
        return self.current_hash
    
    def verify_integrity(self) -> bool:
        """
        Verify the integrity of the audit log.
        
        Returns:
            True if audit chain is valid
        """
        return verify_audit_chain(self.audit_log_path)
    
    def add_decision(
        self,
        pipeline_run_id: str,
        stage_id: str,
        subagent: str,
        decision_type: str,
        rationale: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Add a decision to the database.
        
        Args:
            pipeline_run_id: Pipeline run identifier
            stage_id: Stage identifier
            subagent: Subagent name
            decision_type: Type of decision
            rationale: Short summary
            body: Full searchable text
            metadata: Optional JSON metadata
            
        Returns:
            The ID of the inserted decision
        """
        if not self.conn:
            raise RuntimeError("Memory system not initialized")
        
        return insert_decision(
            self.conn, pipeline_run_id, stage_id, subagent,
            decision_type, rationale, body, metadata
        )
    
    def search_decisions(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search decisions using full-text search.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching decisions
        """
        if not self.conn:
            raise RuntimeError("Memory system not initialized")
        
        return search_decisions(self.conn, query, limit)
    
    def add_shared_fact(
        self,
        pipeline_run_id: str,
        stage_id: str,
        fact_key: str,
        fact_value: str,
        rationale: Optional[str] = None
    ) -> int:
        """
        Add a shared fact to the database.
        
        Args:
            pipeline_run_id: Pipeline run identifier
            stage_id: Stage identifier
            fact_key: Fact key
            fact_value: Fact value
            rationale: Optional rationale
            
        Returns:
            The ID of the inserted fact
        """
        if not self.conn:
            raise RuntimeError("Memory system not initialized")
        
        return insert_shared_fact(
            self.conn, pipeline_run_id, stage_id, fact_key, fact_value, rationale
        )
    
    def search_shared_facts(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search shared facts using full-text search.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching shared facts
        """
        if not self.conn:
            raise RuntimeError("Memory system not initialized")
        
        return search_shared_facts(self.conn, query, limit)
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()