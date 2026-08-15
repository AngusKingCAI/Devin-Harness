#!/usr/bin/env python3
"""
Search episodes from episodic memory.

Usage:
    python search_episodes.py --query <search-term> [options]

Options:
    --query <term>         Search term (required)
    --event-types <types>  Comma-separated event types to search (default: all)
    --limit <number>       Maximum number of results (default: 5)
    --hours <number>       Only search episodes from last N hours (default: 168 = 1 week)
    --importance <level>   Minimum importance level (default: low)
    --session-id <id>      Filter by session identifier (optional)

Output:
    JSON array of matching episodes
"""

import json
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Search episodes from episodic memory')
    parser.add_argument('--query', required=True, help='Search term')
    parser.add_argument('--event-types', help='Comma-separated event types')
    parser.add_argument('--limit', type=int, default=5, help='Maximum results')
    parser.add_argument('--hours', type=int, default=168, help='Search last N hours (default: 1 week)')
    parser.add_argument('--importance', choices=['high', 'medium', 'low'], default='low', help='Minimum importance')
    parser.add_argument('--session-id', help='Filter by session identifier')
    
    args = parser.parse_args()
    
    # Get the memory directory path
    script_dir = Path(__file__).parent.parent
    memory_dir = script_dir / 'memory'
    episodes_file = memory_dir / 'episodes.json'
    
    # Read existing episodes
    try:
        with open(episodes_file, 'r') as f:
            episodes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        episodes = []
    
    # Filter by time
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    cutoff_iso = cutoff_time.isoformat()
    
    recent_episodes = [ep for ep in episodes if ep['timestamp'] >= cutoff_iso]
    
    # Filter by event types if specified
    if args.event_types:
        target_types = [t.strip() for t in args.event_types.split(',')]
        recent_episodes = [ep for ep in recent_episodes if ep['event_type'] in target_types]
    
    # Filter by session ID if specified
    if args.session_id:
        recent_episodes = [ep for ep in recent_episodes if ep.get('session_id') == args.session_id]
    
    # Filter by importance
    importance_order = {'high': 3, 'medium': 2, 'low': 1}
    min_importance = importance_order[args.importance]
    recent_episodes = [
        ep for ep in recent_episodes 
        if importance_order.get(ep['metadata'].get('importance', 'medium'), 2) >= min_importance
    ]
    
    # Simple text search (case-insensitive)
    search_term = args.query.lower()
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
    
    # Sort by timestamp (most recent first) and limit
    matching_episodes.sort(key=lambda x: x['timestamp'], reverse=True)
    matching_episodes = matching_episodes[:args.limit]
    
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
                with open(episodes_file, 'w') as f:
                    json.dump(list(episode_map.values()), f, indent=2)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # If file operations fail, still return results
            pass
    
    # Output as JSON
    print(json.dumps(matching_episodes, indent=2))


if __name__ == '__main__':
    main()