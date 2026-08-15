#!/usr/bin/env python3
"""
Memory MCP Server for Devin CLI

Exposes memory operations as MCP tools that agents can call during operations:
- memory_search: Search episodic memory for relevant episodes
- memory_save: Save new memory entries
- memory_consolidate: Trigger consolidation of recent episodes

Based on research recommendations for transforming event logging into usable memory.

Uses the MCP Python SDK (mcp) to expose tools to Devin CLI.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
import subprocess

# MCP imports
try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    print("MCP library not available. Install with: pip install mcp", file=sys.stderr)
    MCP_AVAILABLE = False
    sys.exit(1)


def get_memory_dir():
    """Get the memory directory path."""
    script_dir = Path(__file__).parent.parent
    memory_dir = script_dir / 'memory'
    return memory_dir


def load_episodes():
    """Load all episodes from episodes.json."""
    memory_dir = get_memory_dir()
    episodes_file = memory_dir / 'episodes.json'
    
    try:
        with open(episodes_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def search_episodes(query: str, limit: int = 5, hours: int = 168, importance: str = None):
    """
    Search episodes for relevant content.
    
    Args:
        query: Search term
        limit: Maximum results to return
        hours: Only search last N hours (default 168 = 1 week)
        importance: Filter by importance level (high, medium, low)
    
    Returns:
        List of matching episodes
    """
    episodes = load_episodes()
    
    if not episodes:
        return []
    
    # Filter by time
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff_time.isoformat()
    
    recent_episodes = [ep for ep in episodes if ep['timestamp'] >= cutoff_iso]
    
    # Filter by importance if specified
    if importance:
        importance_order = {'high': 3, 'medium': 2, 'low': 1}
        min_importance = importance_order.get(importance, 1)
        recent_episodes = [
            ep for ep in recent_episodes 
            if importance_order.get(ep['metadata'].get('importance', 'medium'), 2) >= min_importance
        ]
    
    # Simple text search (case-insensitive)
    search_term = query.lower()
    matching_episodes = []
    
    for ep in recent_episodes:
        # Search in content
        if search_term in ep['content'].lower():
            matching_episodes.append(ep)
            continue
        
        # Search in metadata fields
        metadata = ep.get('metadata', {})
        if metadata.get('file_path') and search_term in metadata['file_path'].lower():
            matching_episodes.append(ep)
            continue
        if metadata.get('tool_name') and search_term in metadata['tool_name'].lower():
            matching_episodes.append(ep)
            continue
        if metadata.get('agent') and search_term in metadata['agent'].lower():
            matching_episodes.append(ep)
    
    # Sort by timestamp (most recent first) and limit
    matching_episodes.sort(key=lambda x: x['timestamp'], reverse=True)
    matching_episodes = matching_episodes[:limit]
    
    # Update access_count for matched episodes
    if matching_episodes:
        try:
            # Create mapping for O(1) lookup
            episode_map = {ep['id']: ep for ep in episodes}
            
            # Update access_count for matched episodes
            updated = False
            for matched_ep in matching_episodes:
                if matched_ep['id'] in episode_map:
                    if 'access_count' not in episode_map[matched_ep['id']]['metadata']:
                        episode_map[matched_ep['id']]['metadata']['access_count'] = 0
                    episode_map[matched_ep['id']]['metadata']['access_count'] += 1
                    updated = True
            
            # Write back if any updates
            if updated:
                memory_dir = get_memory_dir()
                episodes_file = memory_dir / 'episodes.json'
                with open(episodes_file, 'w') as f:
                    json.dump(list(episode_map.values()), f, indent=2)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # If file operations fail, still return results
            pass
    
    return matching_episodes


def save_episode(content: str, importance: str = "medium", event_type: str = "note", 
                agent: str = "Orchestrator", file_path: str = None, 
                tool_name: str = None, outcome: str = None):
    """
    Save a new episode to memory.
    
    Args:
        content: Human-readable description
        importance: high|medium|low
        event_type: research|decision|attempt|fix|review|note
        agent: Agent name
        file_path: Related file path (optional)
        tool_name: Related tool name (optional)
        outcome: success|failure|pending (optional)
    
    Returns:
        Episode ID
    """
    import uuid
    
    episodes = load_episodes()
    
    # Create new episode
    episode = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'session_id': None,  # Will be set by hook if needed
        'event_type': event_type,
        'content': content,
        'metadata': {
            'file_path': file_path,
            'tool_name': tool_name,
            'outcome': outcome,
            'importance': importance,
            'agent': agent,
            'access_count': 0
        }
    }
    
    # Remove None values from metadata
    episode['metadata'] = {k: v for k, v in episode['metadata'].items() if v is not None}
    
    # Append to episodes
    episodes.append(episode)
    
    # Write back to file
    memory_dir = get_memory_dir()
    episodes_file = memory_dir / 'episodes.json'
    
    with open(episodes_file, 'w') as f:
        json.dump(episodes, f, indent=2)
    
    return episode['id']





# MCP Server Setup using FastMCP
mcp = FastMCP(name="memory")


@mcp.tool()
def memory_search(query: str, limit: int = 5, hours: int = 168, importance: str = None) -> str:
    """
    Search episodic memory for relevant past episodes.
    
    Args:
        query: Search term or question
        limit: Maximum results to return (default: 5)
        hours: Search window in hours (default: 168 = 1 week)
        importance: Filter by importance level (high, medium, low)
    
    Returns:
        JSON string with matching episodes
    """
    results = search_episodes(query, limit, hours, importance)
    return json.dumps(results, indent=2)


@mcp.tool()
def memory_save(content: str, importance: str = "medium", event_type: str = "note",
                  agent: str = "Orchestrator", file_path: str = None, 
                  tool_name: str = None, outcome: str = None) -> str:
    """
    Save a new memory entry to episodic memory.
    
    Args:
        content: The memory content to save
        importance: Importance level (high, medium, low)
        event_type: Type of event (research, decision, attempt, fix, review, note)
        agent: Agent that created this memory
        file_path: Related file path (optional)
        tool_name: Related tool name (optional)
        outcome: Outcome (success, failure, pending)
    
    Returns:
        JSON string with episode_id and timestamp
    """
    episode_id = save_episode(content, importance, event_type, agent, file_path, tool_name, outcome)
    return json.dumps({
        'episode_id': episode_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'status': 'saved'
    }, indent=2)


@mcp.tool()
def memory_search_semantic(query: str, limit: int = 5, category: str = None) -> str:
    """
    Search semantic memory for distilled facts.
    
    Args:
        query: Search term or question
        limit: Maximum results to return (default: 5)
        category: Filter by fact category (optional)
    
    Returns:
        JSON string with matching semantic facts
    """
    memory_dir = get_memory_dir()
    semantic_file = memory_dir / 'semantic.json'
    
    try:
        with open(semantic_file, 'r') as f:
            facts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return json.dumps([])
    
    # Filter by category if specified
    if category:
        facts = [f for f in facts if f.get('category') == category]
    
    # Simple text search (case-insensitive)
    search_term = query.lower()
    matching_facts = []
    
    for fact in facts:
        if search_term in fact['fact'].lower():
            matching_facts.append(fact)
    
    # Sort by evidence_count and last_reinforced_at
    matching_facts.sort(key=lambda x: (x['evidence_count'], x['last_reinforced_at']), reverse=True)
    matching_facts = matching_facts[:limit]
    
    # Update access_count for matched facts
    if matching_facts:
        try:
            # Create mapping for O(1) lookup and update
            fact_map = {fact['id']: fact for fact in facts}
            
            # Update access_count for matched facts
            updated = False
            for matched_fact in matching_facts:
                fact_id = matched_fact['id']
                if fact_id in fact_map:
                    if 'access_count' not in fact_map[fact_id]:
                        fact_map[fact_id]['access_count'] = 0
                    fact_map[fact_id]['access_count'] += 1
                    updated = True
            
            # Write back if any updates
            if updated:
                with open(semantic_file, 'w') as f:
                    json.dump(list(fact_map.values()), f, indent=2)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # If file operations fail, still return results
            pass
    
    return json.dumps(matching_facts, indent=2)


@mcp.tool()
def decision_check(pattern: str) -> str:
    """
    Check for applicable procedural decisions for a given pattern.
    
    Args:
        pattern: The pattern to check against decision rules
    
    Returns:
        JSON string with applicable decisions
    """
    memory_dir = get_memory_dir()
    decisions_file = memory_dir / 'decisions.json'
    
    try:
        with open(decisions_file, 'r') as f:
            decisions = json.load(f)
        
        pattern_lower = pattern.lower()
        applicable = []
        
        for decision in decisions:
            if pattern_lower in decision['pattern'].lower():
                applicable.append(decision)
        
        return json.dumps(applicable, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def decision_apply(decision_id: str) -> str:
    """
    Apply a procedural decision and update its statistics.
    
    Args:
        decision_id: The ID of the decision to apply
    
    Returns:
        JSON string with updated decision
    """
    memory_dir = get_memory_dir()
    decisions_file = memory_dir / 'decisions.json'
    
    try:
        with open(decisions_file, 'r') as f:
            decisions = json.load(f)
        
        for decision in decisions:
            if decision['id'] == decision_id:
                decision['last_applied'] = datetime.now(timezone.utc).isoformat()
                decision['apply_count'] = decision.get('apply_count', 0) + 1
                
                with open(decisions_file, 'w') as f:
                    json.dump(decisions, f, indent=2)
                
                return json.dumps(decision, indent=2)
        
        return json.dumps({"error": f"Decision {decision_id} not found"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def decision_update_stats(decision_id: str, success: bool) -> str:
    """
    Update success statistics for a procedural decision.
    
    Args:
        decision_id: The ID of the decision
        success: Whether the application was successful
    
    Returns:
        JSON string with confirmation
    """
    memory_dir = get_memory_dir()
    decisions_file = memory_dir / 'decisions.json'
    
    try:
        with open(decisions_file, 'r') as f:
            decisions = json.load(f)
        
        for decision in decisions:
            if decision['id'] == decision_id:
                current_success_rate = decision.get('success_rate', 0.5)
                new_success_rate = (current_success_rate * 0.9) + (1.0 if success else 0.0) * 0.1
                decision['success_rate'] = new_success_rate
                
                with open(decisions_file, 'w') as f:
                    json.dump(decisions, f, indent=2)
                
                return json.dumps({"status": "updated", "decision_id": decision_id, "success": success}, indent=2)
        
        return json.dumps({"error": f"Decision {decision_id} not found"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def decision_get_confidence_threshold(claim_type: str = "default") -> str:
    """
    Get confidence threshold for a specific type of claim or decision.
    
    Args:
        claim_type: Type of claim (default, information_verification, claim_quality, user_interaction)
    
    Returns:
        JSON string with confidence threshold
    """
    memory_dir = get_memory_dir()
    decisions_file = memory_dir / 'decisions.json'
    
    try:
        with open(decisions_file, 'r') as f:
            decisions = json.load(f)
        
        if claim_type == "information_verification":
            return json.dumps({"threshold": 0.9, "type": "websearch_clarity"}, indent=2)
        elif claim_type == "claim_quality":
            return json.dumps({"threshold": 0.8, "type": "claim_quality"}, indent=2)
        elif claim_type == "user_interaction":
            return json.dumps({"use_ask_user_question": True, "type": "user_interaction"}, indent=2)
        elif claim_type == "orchestration":
            return json.dumps({"propose_implementation": True, "type": "orchestration"}, indent=2)
        else:
            return json.dumps({"threshold": 0.8, "type": "default"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def memory_consolidate(hours: int = 24, method: str = "simple") -> str:
    """
    Trigger consolidation of recent episodes into semantic memory.
    
    Args:
        hours: Only consolidate episodes from last N hours (default: 24)
        method: Extraction method (simple or llm, default: simple)
    
    Returns:
        JSON string with consolidation summary
    """
    try:
        # Run semantic extraction script
        result = subprocess.run(
            [sys.executable, ".devin/scripts/semantic_extract.py", "--hours", str(hours), "--method", method],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            return json.dumps({
                "error": "Consolidation failed",
                "stderr": result.stderr,
                "returncode": result.returncode
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "message": "Consolidation failed due to exception"
        }, indent=2)


def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
