#!/usr/bin/env python3
"""
Semantic Memory Extraction Script

Extracts distilled facts from episodic memory episodes into semantic memory.
Converts raw event logs into persistent, queryable knowledge.

Usage:
    python semantic_extract.py --hours 24
    python semantic_extract.py --episode-id <uuid>
    python semantic_extract.py --session-id <session_id>
"""

import json
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any


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


def load_semantic_memory():
    """Load existing semantic memory from semantic.json."""
    memory_dir = get_memory_dir()
    semantic_file = memory_dir / 'semantic.json'
    
    try:
        with open(semantic_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_semantic_memory(facts: List[Dict[str, Any]]):
    """Save facts to semantic.json."""
    memory_dir = get_memory_dir()
    semantic_file = memory_dir / 'semantic.json'
    
    with open(semantic_file, 'w') as f:
        json.dump(facts, f, indent=2)


def filter_episodes_by_hours(episodes: List[Dict], hours: int) -> List[Dict]:
    """Filter episodes from the last N hours."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff_time.isoformat()
    
    return [ep for ep in episodes if ep['timestamp'] >= cutoff_iso]


def filter_episodes_by_session(episodes: List[Dict], session_id: str) -> List[Dict]:
    """Filter episodes by session ID."""
    return [ep for ep in episodes if ep.get('session_id') == session_id]


def filter_episodes_by_id(episodes: List[Dict], episode_id: str) -> List[Dict]:
    """Filter episodes by specific episode ID."""
    return [ep for ep in episodes if ep['id'] == episode_id]


def text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using SequenceMatcher.
    
    Returns a float between 0.0 (no similarity) and 1.0 (identical).
    """
    from difflib import SequenceMatcher
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def deduplicate_facts(new_facts: List[Dict], existing_facts: List[Dict], similarity_threshold: float = 0.7) -> List[Dict]:
    """
    Deduplicate facts against existing semantic memory using similarity matching.
    
    A fact is a duplicate if it has high similarity to an existing fact.
    If duplicate found, increment evidence_count and update last_reinforced_at.
    """
    merged_facts = existing_facts.copy()
    
    for new_fact in new_facts:
        new_content = new_fact['fact']
        duplicate_found = False
        
        # Check against existing facts for similarity
        for existing_fact in merged_facts:
            existing_content = existing_fact['fact']
            
            # Calculate similarity
            similarity = text_similarity(new_content, existing_content)
            
            if similarity >= similarity_threshold:
                # Found a duplicate - update existing fact
                existing_fact['evidence_count'] += 1
                existing_fact['last_reinforced_at'] = new_fact['created_at']
                existing_fact['source_episodes'].extend(new_fact['source_episodes'])
                # Remove duplicates from source_episodes
                existing_fact['source_episodes'] = list(set(existing_fact['source_episodes']))
                duplicate_found = True
                break
        
        if not duplicate_found:
            # Add new fact
            merged_facts.append(new_fact)
    
    return merged_facts


def extract_facts_simple(episodes: List[Dict]) -> List[Dict[str, Any]]:
    """
    Improved rule-based fact extraction (no LLM required).
    
    Extracts only high-quality distilled facts from episodes.
    More selective to avoid creating low-quality "facts" from routine operations.
    """
    facts = []
    
    for episode in episodes:
        # Only extract from high-importance episodes
        if episode.get('metadata', {}).get('importance') != 'high':
            continue
        
        content = episode['content']
        
        # Skip if content is too long (likely not a distilled fact)
        if len(content) > 300:
            continue
        
        # Skip if content is too short (likely meaningless)
        if len(content) < 20:
            continue
        
        # Skip if it's just a tool call log
        if content.startswith(('Executed command', 'Wrote file', 'Read file', 'Edited file', 'Tool executed')):
            continue
        
        # Skip if it's a user prompt (not distilled knowledge)
        if content.startswith('User prompt:'):
            continue
        
        # Skip if it's a subagent task description (not distilled knowledge)
        if content.startswith('Subagent task:'):
            continue
        
        # Skip if it's a session or hook event (not distilled knowledge)
        if content.startswith(('Session', 'Hook', 'Episode')):
            continue
        
        # Skip if it contains file paths (likely operational, not knowledge)
        if 'C:\\' in content or '/' in content:
            continue
        
        # Skip if it's just logging output
        if content.startswith(('Output from command', 'Exit code')):
            continue
        
        # Additional quality filters
        # Skip if content is mostly special characters or numbers
        if sum(c.isalnum() or c.isspace() for c in content) / len(content) < 0.7:
            continue
        
        # Only extract from specific event types that contain distilled knowledge
        valid_event_types = ['fix', 'research', 'decision']
        if episode.get('event_type') not in valid_event_types:
            continue
        
        # Create fact from episode
        fact = {
            'id': f"fact_{episode['id']}",
            'fact': content,
            'source_episodes': [episode['id']],
            'confidence': 0.8,  # Will be recalculated after deduplication
            'evidence_count': 1,
            'category': infer_category(episode),
            'created_at': episode['timestamp'],
            'last_reinforced_at': episode['timestamp'],
            'access_count': 0
        }
        
        facts.append(fact)
    
    return facts


def infer_category(episode: Dict) -> str:
    """Infer fact category from episode metadata."""
    event_type = episode.get('event_type', 'note')
    
    category_map = {
        'research': 'research',
        'decision': 'decision',
        'fix': 'fix',
        'attempt': 'pattern',
        'review': 'review',
        'note': 'note',
        'benchmark': 'benchmark'
    }
    
    return category_map.get(event_type, 'general')


def calculate_confidence(fact: Dict) -> float:
    """
    Calculate confidence score for a fact based on multiple factors.
    
    Factors:
    - evidence_count: More evidence = higher confidence
    - source_episodes: More diverse sources = higher confidence
    - access_count: More access = higher confidence
    - time_since_creation: Very old facts may have lower confidence
    """
    evidence_count = fact.get('evidence_count', 1)
    source_count = len(fact.get('source_episodes', []))
    access_count = fact.get('access_count', 0)
    
    # Base confidence from evidence
    confidence = 0.5 + (min(evidence_count, 10) / 20)  # Max 1.0 at 10+ evidence
    
    # Boost from diverse sources
    if source_count > 1:
        confidence += min(source_count / 20, 0.2)  # Max +0.2 boost
    
    # Boost from access patterns
    if access_count > 0:
        confidence += min(access_count / 50, 0.1)  # Max +0.1 boost
    
    # Cap at 1.0
    return min(confidence, 1.0)


def extract_facts_llm(episodes: List[Dict]) -> List[Dict[str, Any]]:
    """
    LLM-based fact extraction (placeholder for Phase 2).
    
    This would use an LLM to:
    - Analyze episodes for distilled facts
    - Generalize specific experiences into reusable patterns
    - Identify contradictions between episodes
    - Extract implicit knowledge not explicitly stated
    
    For now, falls back to simple extraction.
    """
    print("LLM-based extraction not yet implemented. Using simple rule-based extraction.", file=sys.stderr)
    return extract_facts_simple(episodes)


def main():
    parser = argparse.ArgumentParser(description='Extract semantic facts from episodic memory')
    parser.add_argument('--hours', type=int, default=24, help='Extract from last N hours (default: 24)')
    parser.add_argument('--episode-id', help='Extract from specific episode ID')
    parser.add_argument('--session-id', help='Extract from specific session ID')
    parser.add_argument('--method', choices=['simple', 'llm'], default='simple', 
                       help='Extraction method (default: simple)')
    parser.add_argument('--similarity', type=float, default=0.7, 
                       help='Similarity threshold for deduplication (default: 0.7)')
    
    args = parser.parse_args()
    
    # Load episodes
    episodes = load_episodes()
    
    if not episodes:
        print("No episodes found in episodic memory.", file=sys.stderr)
        return
    
    # Filter episodes based on arguments
    if args.episode_id:
        episodes = filter_episodes_by_id(episodes, args.episode_id)
    elif args.session_id:
        episodes = filter_episodes_by_session(episodes, args.session_id)
    else:
        episodes = filter_episodes_by_hours(episodes, args.hours)
    
    if not episodes:
        print(f"No episodes found matching criteria.", file=sys.stderr)
        return
    
    print(f"Processing {len(episodes)} episodes...", file=sys.stderr)
    
    # Extract facts
    if args.method == 'llm':
        facts = extract_facts_llm(episodes)
    else:
        facts = extract_facts_simple(episodes)
    
    if not facts:
        print("No facts extracted from episodes.", file=sys.stderr)
        return
    
    print(f"Extracted {len(facts)} facts.", file=sys.stderr)
    
    # Load existing semantic memory
    existing_facts = load_semantic_memory()
    
    # Deduplicate and merge
    merged_facts = deduplicate_facts(facts, existing_facts, similarity_threshold=args.similarity)
    
    # Recalculate confidence for all facts
    for fact in merged_facts:
        fact['confidence'] = calculate_confidence(fact)
    
    # Save semantic memory
    save_semantic_memory(merged_facts)
    
    print(f"Semantic memory now contains {len(merged_facts)} facts.", file=sys.stderr)
    
    # Output summary
    print(json.dumps({
        'episodes_processed': len(episodes),
        'facts_extracted': len(facts),
        'total_facts': len(merged_facts),
        'new_facts': len(merged_facts) - len(existing_facts)
    }, indent=2))


if __name__ == '__main__':
    main()
