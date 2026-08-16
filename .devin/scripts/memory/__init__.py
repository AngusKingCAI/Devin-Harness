"""Memory system module for audit logging and decision database."""

from memory.audit import append_audit, verify_audit_chain, compute_hash
from memory.decisions import (
    verify_fts5, initialize_schema, insert_decision, search_decisions,
    insert_shared_fact, search_shared_facts
)
from memory.memory import MemorySystem

__all__ = [
    'append_audit',
    'verify_audit_chain', 
    'compute_hash',
    'verify_fts5',
    'initialize_schema',
    'insert_decision',
    'search_decisions',
    'insert_shared_fact',
    'search_shared_facts',
    'MemorySystem'
]