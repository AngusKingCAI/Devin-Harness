#!/usr/bin/env python3
"""
Recurrence Detection for Episodic Memory

Identifies similar patterns that repeat across episodes to enable smart consolidation.
Detects when similar events occur repeatedly, indicating patterns that should be consolidated.

Usage:
    python detect_recurrence.py --hours 168 --similarity 0.7
"""

import json
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher


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


def filter_episodes_by_hours(episodes: List[Dict], hours: int) -> List[Dict]:
    """Filter episodes from the last N hours."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff_time.isoformat()
    
    return [ep for ep in episodes if ep['timestamp'] >= cutoff_iso]


def text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using SequenceMatcher.
    
    Returns a float between 0.0 (no similarity) and 1.0 (identical).
    """
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def find_recurring_patterns(episodes: List[Dict], similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
    """
    Find recurring patterns in episodes.
    
    Args:
        episodes: List of episodes to analyze
        similarity_threshold: Minimum similarity to consider a recurrence (default 0.7)
    
    Returns:
        List of recurring patterns with metadata
    """
    patterns = []
    seen_patterns = {}
    
    for i, episode in enumerate(episodes):
        content = episode['content']
        
        # Skip very short content (not meaningful patterns)
        if len(content) < 20:
            continue
        
        # Skip user prompts (not patterns we want to consolidate)
        if content.startswith('User prompt:'):
            continue
        
        # Check against previously seen episodes
        for j, other_episode in enumerate(episodes[i+1:], i+1):
            other_content = other_episode['content']
            
            # Skip if other episode is too short
            if len(other_content) < 20:
                continue
            
            # Calculate similarity
            similarity = text_similarity(content, other_content)
            
            if similarity >= similarity_threshold:
                # Found a recurring pattern
                pattern_key = min(content, other_content)  # Use shorter as key
                
                if pattern_key not in seen_patterns:
                    seen_patterns[pattern_key] = {
                        'pattern': pattern_key,
                        'occurrences': [],
                        'episodes': [],
                        'similarity_scores': []
                    }
                
                # Record this occurrence
                seen_patterns[pattern_key]['occurrences'].append({
                    'episode_id': episode['id'],
                    'timestamp': episode['timestamp'],
                    'similarity': similarity
                })
                seen_patterns[pattern_key]['episodes'].append(episode['id'])
                seen_patterns[pattern_key]['similarity_scores'].append(similarity)
    
    # Convert to list and add metadata
    for pattern_data in seen_patterns.values():
        if len(pattern_data['occurrences']) >= 2:  # Only include patterns that appear at least twice
            patterns.append({
                'pattern': pattern_data['pattern'],
                'occurrence_count': len(pattern_data['occurrences']),
                'episodes': pattern_data['episodes'],
                'average_similarity': sum(pattern_data['similarity_scores']) / len(pattern_data['similarity_scores']),
                'first_occurrence': min(occ['timestamp'] for occ in pattern_data['occurrences']),
                'last_occurrence': max(occ['timestamp'] for occ in pattern_data['occurrences']),
                'timespan_hours': (datetime.fromisoformat(max(occ['timestamp'] for occ in pattern_data['occurrences'])) - 
                                   datetime.fromisoformat(min(occ['timestamp'] for occ in pattern_data['occurrences']))).total_seconds() / 3600
            })
    
    # Sort by occurrence count (most frequent first)
    patterns.sort(key=lambda x: x['occurrence_count'], reverse=True)
    
    return patterns


def main():
    parser = argparse.ArgumentParser(description='Detect recurring patterns in episodic memory')
    parser.add_argument('--hours', type=int, default=168, help='Analyze last N hours (default: 168 = 1 week)')
    parser.add_argument('--similarity', type=float, default=0.7, help='Similarity threshold (default: 0.7)')
    parser.add_argument('--min-occurrences', type=int, default=2, help='Minimum occurrences to be considered recurring (default: 2)')
    
    args = parser.parse_args()
    
    # Load episodes
    episodes = load_episodes()
    
    if not episodes:
        print("No episodes found in episodic memory.", file=sys.stderr)
        return
    
    # Filter by time
    recent_episodes = filter_episodes_by_hours(episodes, args.hours)
    
    if not recent_episodes:
        print(f"No episodes found in last {args.hours} hours.", file=sys.stderr)
        return
    
    print(f"Analyzing {len(recent_episodes)} episodes for recurring patterns...", file=sys.stderr)
    
    # Find recurring patterns
    patterns = find_recurring_patterns(recent_episodes, args.similarity)
    
    # Filter by minimum occurrences
    patterns = [p for p in patterns if p['occurrence_count'] >= args.min_occurrences]
    
    if not patterns:
        print("No recurring patterns found.", file=sys.stderr)
        return
    
    print(f"Found {len(patterns)} recurring patterns.", file=sys.stderr)
    
    # Output results
    output = {
        'episodes_analyzed': len(recent_episodes),
        'time_window_hours': args.hours,
        'similarity_threshold': args.similarity,
        'recurring_patterns': patterns
    }
    
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
