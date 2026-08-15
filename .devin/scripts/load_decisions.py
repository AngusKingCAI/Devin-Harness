#!/usr/bin/env python3
"""
Load and apply procedural decisions from decisions.json.

This script provides functions to:
- Load decision rules from decisions.json
- Check if a decision should be applied
- Track decision application and success rates
- Update decision statistics

Usage:
    python load_decisions.py --check "<pattern>"
    python load_decisions.py --apply "<decision_id>"
    python load_decisions.py --update-stats "<decision_id>" --success <true/false>
"""

import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional


def get_memory_dir():
    """Get the memory directory path."""
    script_dir = Path(__file__).parent.parent
    memory_dir = script_dir / 'memory'
    return memory_dir


def load_decisions() -> List[Dict[str, Any]]:
    """Load all decisions from decisions.json."""
    memory_dir = get_memory_dir()
    decisions_file = memory_dir / 'decisions.json'
    
    try:
        with open(decisions_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_decisions(decisions: List[Dict[str, Any]]):
    """Save decisions to decisions.json."""
    memory_dir = get_memory_dir()
    decisions_file = memory_dir / 'decisions.json'
    
    with open(decisions_file, 'w') as f:
        json.dump(decisions, f, indent=2)


def find_applicable_decisions(pattern: str) -> List[Dict[str, Any]]:
    """
    Find decisions that apply to a given pattern.
    
    Args:
        pattern: The pattern to match against decision rules
    
    Returns:
        List of applicable decisions
    """
    decisions = load_decisions()
    pattern_lower = pattern.lower()
    
    applicable = []
    for decision in decisions:
        if pattern_lower in decision['pattern'].lower():
            applicable.append(decision)
    
    return applicable


def apply_decision(decision_id: str) -> Dict[str, Any]:
    """
    Apply a decision and update its statistics.
    
    Args:
        decision_id: The ID of the decision to apply
    
    Returns:
        The updated decision
    """
    decisions = load_decisions()
    
    for decision in decisions:
        if decision['id'] == decision_id:
            decision['last_applied'] = datetime.now(timezone.utc).isoformat()
            decision['apply_count'] = decision.get('apply_count', 0) + 1
            save_decisions(decisions)
            return decision
    
    raise ValueError(f"Decision {decision_id} not found")


def update_decision_stats(decision_id: str, success: bool):
    """
    Update success statistics for a decision.
    
    Args:
        decision_id: The ID of the decision
        success: Whether the application was successful
    """
    decisions = load_decisions()
    
    for decision in decisions:
        if decision['id'] == decision_id:
            current_success_rate = decision.get('success_rate', 0.5)
            apply_count = decision.get('apply_count', 1)
            
            # Calculate new success rate using exponential moving average
            new_success_rate = (current_success_rate * 0.9) + (1.0 if success else 0.0) * 0.1
            
            decision['success_rate'] = new_success_rate
            save_decisions(decisions)
            return
    
    raise ValueError(f"Decision {decision_id} not found")


def get_confidence_for_claim(claim: str) -> float:
    """
    Get confidence threshold for a claim based on decision rules.
    
    Args:
        claim: The claim to evaluate
    
    Returns:
        Confidence threshold (0.0-1.0)
    """
    decisions = load_decisions()
    
    for decision in decisions:
        if decision['category'] == 'claim_quality':
            return decision.get('confidence_threshold', 0.8)
    
    return 0.8  # Default threshold


def should_websearch_for_clarity(confidence: float) -> bool:
    """
    Determine if websearch should be used for clarity based on confidence.
    
    Args:
        confidence: Current confidence level (0.0-1.0)
    
    Returns:
        True if websearch should be used
    """
    decisions = load_decisions()
    
    for decision in decisions:
        if decision['category'] == 'information_verification':
            threshold = decision.get('confidence_threshold', 0.9)
            return confidence < threshold
    
    return confidence < 0.9  # Default threshold


def should_use_ask_user_question() -> bool:
    """
    Determine if ask_user_question should be used for user interaction.
    
    Returns:
        True if ask_user_question should be used
    """
    decisions = load_decisions()
    
    for decision in decisions:
        if decision['category'] == 'user_interaction':
            return decision.get('enforcement') == 'automatic'
    
    return True  # Default to using ask_user_question


def main():
    parser = argparse.ArgumentParser(description='Load and apply procedural decisions')
    parser.add_argument('--check', help='Check for applicable decisions for a pattern')
    parser.add_argument('--apply', help='Apply a specific decision by ID')
    parser.add_argument('--update-stats', help='Update statistics for a decision by ID')
    parser.add_argument('--success', type=bool, help='Success status for stats update')
    
    args = parser.parse_args()
    
    if args.check:
        applicable = find_applicable_decisions(args.check)
        print(json.dumps(applicable, indent=2))
    elif args.apply:
        decision = apply_decision(args.apply)
        print(json.dumps(decision, indent=2))
    elif args.update_stats:
        update_decision_stats(args.update_stats, args.success)
        print(f"Updated stats for decision {args.update_stats}")
    else:
        # List all decisions
        decisions = load_decisions()
        print(json.dumps(decisions, indent=2))


if __name__ == '__main__':
    main()
