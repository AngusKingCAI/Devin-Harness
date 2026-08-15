---
triggers: ["user", "model"]
description: Search semantic memory for distilled facts and patterns
subagent: true
---

# Semantic Query Skill

## Purpose
Search the semantic memory at `.devin/memory/semantic.json` for distilled facts and patterns.

## When to Use
- When you need general knowledge rather than specific past events
- When looking for established patterns and best practices
- When you want facts that have been reinforced across multiple episodes
- When searching for categories of knowledge (research, fix, decision, etc.)

## Procedure

1. **Identify Query Terms**: Determine what kind of knowledge you need
   - Focus on concepts, patterns, or general principles
   - Consider the category (research, fix, decision, pattern, etc.)
   - Use broader terms than episodic search

2. **Search Semantic Memory**: Use the semantic extraction script
   ```
   Run: python .devin/scripts/semantic_extract.py --help
   Or directly read: .devin/memory/semantic.json
   ```

3. **Analyze Results**: Review distilled facts
   - Check evidence_count (higher = more reinforced)
   - Look at last_reinforced_at (recency)
   - Consider category relevance
   - Review confidence scores

4. **Apply Knowledge**: Use the distilled facts
   - Apply reinforced patterns to current task
   - Consider facts with high evidence_count as reliable
   - Use category information to narrow scope
   - Reference fact IDs for traceability

## Differences from Episodic Search

**Episodic Memory (memory-query skill):**
- Specific events: "On 2025-06-18 we fixed X by doing Y"
- Time-bound: Search within specific time windows
- Raw experiences: Unprocessed event logs
- Use case: Finding specific past solutions

**Semantic Memory (this skill):**
- Distilled facts: "Always check file permissions before running exec"
- Time-independent: Facts persist across sessions
- Processed knowledge: Extracted and deduplicated patterns
- Use case: Finding general principles and best practices

## Example Usage

**Scenario**: Learning best practices for MCP implementation

```
Query: "MCP server implementation"
Category: "fix"
Results: 
- "Use FastMCP from mcp.server.fastmcp instead of Server class" (evidence_count: 2)
- "STDIO transport for local CLI-based servers" (evidence_count: 1)
Apply: Use FastMCP for new MCP server development
```

## Tips

- Semantic memory contains higher-level knowledge than episodic
- Facts with higher evidence_count are more reliable
- Categories help narrow search scope
- Semantic memory is automatically updated via SessionEnd hook
- Facts are deduplicated and reinforced over time
