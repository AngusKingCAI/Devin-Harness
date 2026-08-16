"""SQLite decision database with FTS5 full-text search."""

import logging
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

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


def verify_fts5(conn: sqlite3.Connection) -> None:
    """
    Verify FTS5 is available in the SQLite build.
    
    Args:
        conn: SQLite connection
        
    Raises:
        RuntimeError: If FTS5 is not available
    """
    logger.info("Verifying FTS5 availability...")
    
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
        logger.info("FTS5 is available")
    except sqlite3.OperationalError as e:
        if "no such module: fts5" in str(e):
            raise RuntimeError(
                "FTS5 is not available in your SQLite build. "
                "Install pysqlite3-binary (pip install pysqlite3-binary) "
                "or rebuild Python with SQLITE_ENABLE_FTS5."
            ) from e
        raise


def initialize_schema(conn: sqlite3.Connection) -> None:
    """
    Initialize the decisions database schema with FTS5.
    
    Args:
        conn: SQLite connection
    """
    logger.info("Initializing decisions database schema...")
    
    # Main decisions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            pipeline_run_id TEXT NOT NULL,
            stage_id    TEXT NOT NULL,
            subagent    TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            rationale   TEXT NOT NULL,
            body        TEXT NOT NULL,
            metadata    TEXT
        )
    """)
    
    # FTS5 virtual table for full-text search
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts
        USING fts5(body, content='decisions', content_rowid='id')
    """)
    
    # Triggers to keep FTS in sync
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
            INSERT INTO decisions_fts(rowid, body) VALUES (new.id, new.body);
        END
    """)
    
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON decisions BEGIN
            INSERT INTO decisions_fts(decisions_fts, rowid, body)
                VALUES ('delete', old.id, old.body);
        END
    """)
    
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON decisions BEGIN
            INSERT INTO decisions_fts(decisions_fts, rowid, body)
                VALUES ('delete', old.id, old.body);
            INSERT INTO decisions_fts(rowid, body) VALUES (new.id, new.body);
        END
    """)
    
    # Shared facts table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_facts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            pipeline_run_id TEXT NOT NULL,
            stage_id    TEXT NOT NULL,
            fact_key    TEXT NOT NULL,
            fact_value  TEXT NOT NULL,
            rationale   TEXT
        )
    """)
    
    # FTS5 for shared facts
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS shared_facts_fts
        USING fts5(fact_key, fact_value, content='shared_facts', content_rowid='id')
    """)
    
    # Triggers for shared_facts
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS shared_facts_ai AFTER INSERT ON shared_facts BEGIN
            INSERT INTO shared_facts_fts(rowid, fact_key, fact_value) 
                VALUES (new.id, new.fact_key, new.fact_value);
        END
    """)
    
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS shared_facts_ad AFTER DELETE ON shared_facts BEGIN
            INSERT INTO shared_facts_fts(shared_facts_fts, rowid, fact_key, fact_value)
                VALUES ('delete', old.id, old.fact_key, old.fact_value);
        END
    """)
    
    # Connection pragmas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    
    logger.info("Schema initialized successfully")


def insert_decision(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    stage_id: str,
    subagent: str,
    decision_type: str,
    rationale: str,
    body: str,
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    """
    Insert a decision into the database.
    
    Args:
        conn: SQLite connection
        pipeline_run_id: Pipeline run identifier
        stage_id: Stage identifier
        subagent: Subagent name
        decision_type: Type of decision (stage_output, tool_choice, etc.)
        rationale: Short summary
        body: Full searchable text
        metadata: Optional JSON metadata
        
    Returns:
        The ID of the inserted decision
    """
    logger.info(f"Inserting decision: {decision_type} for stage {stage_id}")
    
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metadata_json = json.dumps(metadata) if metadata else None
    
    cursor = conn.execute(
        """
        INSERT INTO decisions (ts, pipeline_run_id, stage_id, subagent, decision_type, rationale, body, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, pipeline_run_id, stage_id, subagent, decision_type, rationale, body, metadata_json)
    )
    
    decision_id = cursor.lastrowid
    logger.debug(f"Decision inserted with ID: {decision_id}")
    return decision_id


def search_decisions(conn: sqlite3.Connection, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search decisions using FTS5 full-text search.
    
    Args:
        conn: SQLite connection
        query: Search query for FTS5
        limit: Maximum number of results
        
    Returns:
        List of matching decisions with BM25 scores
    """
    logger.info(f"Searching decisions with query: {query}")
    
    cursor = conn.execute(
        """
        SELECT d.id, d.ts, d.pipeline_run_id, d.stage_id, d.subagent, d.decision_type, 
               d.rationale, d.body, d.metadata, bm25(decisions_fts) AS score
        FROM decisions_fts
        JOIN decisions d ON decisions_fts.rowid = d.id
        WHERE decisions_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (query, limit)
    )
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "id": row[0],
            "ts": row[1],
            "pipeline_run_id": row[2],
            "stage_id": row[3],
            "subagent": row[4],
            "decision_type": row[5],
            "rationale": row[6],
            "body": row[7],
            "metadata": json.loads(row[8]) if row[8] else None,
            "score": row[9]
        })
    
    logger.info(f"Found {len(results)} decisions matching query")
    return results


def insert_shared_fact(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    stage_id: str,
    fact_key: str,
    fact_value: str,
    rationale: Optional[str] = None
) -> int:
    """
    Insert a shared fact into the database.
    
    Args:
        conn: SQLite connection
        pipeline_run_id: Pipeline run identifier
        stage_id: Stage identifier
        fact_key: Fact key
        fact_value: Fact value
        rationale: Optional rationale
        
    Returns:
        The ID of the inserted fact
    """
    logger.info(f"Inserting shared fact: {fact_key}")
    
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    cursor = conn.execute(
        """
        INSERT INTO shared_facts (ts, pipeline_run_id, stage_id, fact_key, fact_value, rationale)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ts, pipeline_run_id, stage_id, fact_key, fact_value, rationale)
    )
    
    fact_id = cursor.lastrowid
    logger.debug(f"Shared fact inserted with ID: {fact_id}")
    return fact_id


def search_shared_facts(conn: sqlite3.Connection, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search shared facts using FTS5 full-text search.
    
    Args:
        conn: SQLite connection
        query: Search query for FTS5
        limit: Maximum number of results
        
    Returns:
        List of matching shared facts
    """
    logger.info(f"Searching shared facts with query: {query}")
    
    cursor = conn.execute(
        """
        SELECT f.id, f.ts, f.pipeline_run_id, f.stage_id, f.fact_key, f.fact_value, f.rationale
        FROM shared_facts_fts
        JOIN shared_facts f ON shared_facts_fts.rowid = f.id
        WHERE shared_facts_fts MATCH ?
        LIMIT ?
        """,
        (query, limit)
    )
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "id": row[0],
            "ts": row[1],
            "pipeline_run_id": row[2],
            "stage_id": row[3],
            "fact_key": row[4],
            "fact_value": row[5],
            "rationale": row[6]
        })
    
    logger.info(f"Found {len(results)} shared facts matching query")
    return results