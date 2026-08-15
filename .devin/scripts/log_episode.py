#!/usr/bin/env python3
"""
Log an episode to the episodic memory event log.

Usage:
    python log_episode.py --event-type <type> --content <content> [options]

Event types:
    - research: Research findings, discoveries, file locations
    - decision: Architectural decisions, implementation plans
    - attempt: Implementation attempts, changes made
    - fix: Successful fixes, verified solutions
    - review: Review findings, validation outcomes
    - note: General notes, session summaries

Options:
    --event-type <type>    Type of event (required)
    --content <content>    Human-readable description (required)
    --file-path <path>     Related file path (optional)
    --tool-name <name>     Related tool name (optional)
    --outcome <outcome>    success|failure|pending (optional)
    --importance <level>   high|medium|low (optional)
    --session-id <id>      Session identifier (optional)
"""

import json
import uuid
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Log an episode to episodic memory')
    parser.add_argument('--event-type', required=True, help='Type of event')
    parser.add_argument('--content', help='Human-readable description')
    parser.add_argument('--file-path', help='Related file path')
    parser.add_argument('--tool-name', help='Related tool name')
    parser.add_argument('--outcome', choices=['success', 'failure', 'pending'], help='Outcome')
    parser.add_argument('--importance', choices=['high', 'medium', 'low'], default='medium', help='Importance level')
    parser.add_argument('--session-id', help='Session identifier')
    parser.add_argument('--agent', help='Agent name (e.g., researcher, planner, implementor, reviewer)')
    parser.add_argument('--from-stdin', action='store_true', help='Read hook event data from stdin')
    
    args = parser.parse_args()
    
    # Read hook event data from stdin if requested
    hook_data = {}
    if args.from_stdin:
        try:
            import sys
            hook_data = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            hook_data = {}
    
    # Extract information from hook data if available
    if hook_data:
        # Override with hook data if provided
        args.session_id = hook_data.get('session_id', args.session_id)
        args.tool_name = hook_data.get('tool_name', args.tool_name)
        
        # Try to extract agent information from hook data only if not already set via --agent
        # Explicit --agent argument takes precedence over hook data
        if not args.agent:
            # First check for run_subagent tool which has agent name in tool_input.profile
            if hook_data.get('tool_name') == 'run_subagent':
                tool_input = hook_data.get('tool_input', {})
                args.agent = tool_input.get('profile', None)
                # Set event type to research for subagent tasks if not explicitly set
                if args.event_type == 'attempt':
                    args.event_type = 'research'
            # Then check for general agent fields
            if not args.agent:
                args.agent = hook_data.get('agent', hook_data.get('agent_name', None))
            # Default to Orchestrator if still no agent
            if not args.agent:
                args.agent = 'Orchestrator'
        
        # Generate content from hook data if not provided
        if not args.content:
            # Handle UserPromptSubmit events (user messages)
            if 'prompt' in hook_data or 'user_message' in hook_data:
                user_prompt = hook_data.get('prompt', hook_data.get('user_message', ''))
                args.content = f"User prompt: {user_prompt[:200]}..." if len(user_prompt) > 200 else f"User prompt: {user_prompt}"
            else:
                # Handle tool events
                tool_name = hook_data.get('tool_name', 'unknown')
                tool_input = hook_data.get('tool_input', {})
                tool_result = hook_data.get('tool_result', {})
                
                # Generate descriptive content based on tool
                if tool_name == 'run_subagent':
                    task = tool_input.get('task', 'unknown task')
                    profile = tool_input.get('profile', 'unknown agent')
                    args.content = f"Subagent task: {task[:200]}..." if len(task) > 200 else f"Subagent task: {task}"
                elif tool_name == 'edit':
                    file_path = tool_input.get('file_path', 'unknown file')
                    args.content = f"Edited file: {file_path}"
                    args.file_path = file_path
                elif tool_name == 'exec':
                    command = tool_input.get('command', 'unknown command')
                    args.content = f"Executed command: {command}"
                elif tool_name == 'write':
                    file_path = tool_input.get('file_path', 'unknown file')
                    args.content = f"Wrote file: {file_path}"
                    args.file_path = file_path
                elif tool_name == 'read':
                    file_path = tool_input.get('file_path', 'unknown file')
                    args.content = f"Read file: {file_path}"
                    args.file_path = file_path
                else:
                    args.content = f"Tool executed: {tool_name}"
        
        # Extract outcome from tool result if available
        if not args.outcome and 'tool_response' in hook_data:
            result = hook_data['tool_response']
            if isinstance(result, dict):
                args.outcome = 'success' if result.get('success', True) else 'failure'
    
    # Require content either from argument or generated from hook data
    if not args.content:
        parser.error("--content is required or must be generated from --from-stdin data")
    
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
    
    # Create new episode
    episode = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'session_id': args.session_id,
        'event_type': args.event_type,
        'content': args.content,
        'metadata': {
            'file_path': args.file_path,
            'tool_name': args.tool_name,
            'outcome': args.outcome,
            'importance': args.importance,
            'agent': args.agent
        }
    }
    
    # Remove None values from metadata
    episode['metadata'] = {k: v for k, v in episode['metadata'].items() if v is not None}
    
    # Append to episodes
    episodes.append(episode)
    
    # Write back to file
    with open(episodes_file, 'w') as f:
        json.dump(episodes, f, indent=2)
    
    # Output the episode ID for reference
    print(json.dumps({'episode_id': episode['id'], 'timestamp': episode['timestamp']}))


if __name__ == '__main__':
    main()