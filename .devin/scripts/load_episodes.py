#!/usr/bin/env python3
"""
Load relevant episodes from episodic memory for session start.

Usage:
    python load_episodes.py [options]

Options:
    --limit <number>        Maximum number of episodes to load (default: 10)
    --hours <number>        Only load episodes from last N hours (default: 24)
    --event-types <types>   Comma-separated event types to load (default: all)
    --importance <level>    Minimum importance level (default: medium)
    --session-id <id>       Current session identifier (optional)

Output:
    JSON array of relevant episodes for injection into agent context
"""

import json
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Load relevant episodes from episodic memory')
    parser.add_argument('--limit', type=int, default=10, help='Maximum episodes to load')
    parser.add_argument('--hours', type=int, default=24, help='Only load from last N hours')
    parser.add_argument('--event-types', help='Comma-separated event types')
    parser.add_argument('--importance', choices=['high', 'medium', 'low'], default='medium', help='Minimum importance')
    parser.add_argument('--session-id', help='Current session identifier')
    
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
    
    # Filter by importance
    importance_order = {'high': 3, 'medium': 2, 'low': 1}
    min_importance = importance_order[args.importance]
    recent_episodes = [
        ep for ep in recent_episodes 
        if importance_order.get(ep['metadata'].get('importance', 'medium'), 2) >= min_importance
    ]
    
    # Sort by timestamp (most recent first) and limit
    recent_episodes.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_episodes = recent_episodes[:args.limit]
    
    # Output as JSON
    print(json.dumps(recent_episodes, indent=2))


if __name__ == '__main__':
    main()