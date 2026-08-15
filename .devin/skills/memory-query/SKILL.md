---
triggers: ["user", "model"]
description: Search episodic memory for relevant past experiences
subagent: true
---

# Memory Query Skill

## Purpose
Search the episodic memory at `.devin/memory/episodes.json` for information relevant to the current task.

## When to Use
- Before starting a complex task to check for similar past experiences
- When encountering errors to find known solutions
- When making architectural decisions to reference past patterns
- When you're stuck and need to learn from previous sessions

## Procedure

1. **Extract Key Terms**: Identify 3-5 key terms from the current task
   - Focus on the core problem, technology, or domain
   - Include error messages if applicable
   - Consider both technical and conceptual terms

2. **Search Memory**: Use the MCP memory tool to search episodes
   ```
   Call: mcp__memory__memory_search
   Parameters:
   - query: "<key terms>"
   - limit: 5 (default)
   - hours: 168 (default - 1 week, adjust based on recency needs)
   - importance: "high" (optional, for critical decisions)
   ```

3. **Analyze Results**: Review the returned episodes for relevance
   - Check episode content for similar patterns
   - Look for successful solutions to similar problems
   - Note any warnings or failures related to your current task
   - Consider the recency and importance of results

4. **Apply Learnings**: Incorporate relevant findings into your current task
   - Apply successful patterns from past solutions
   - Avoid known pitfalls mentioned in episodes
   - Reference specific episode IDs when documenting your approach
   - If no relevant results found, proceed with standard approach

## Example Usage

**Scenario**: Encountering file permission errors

```
Key terms: "file permissions", "access denied", "exec command"
Search: mcp__memory__memory_search(query="file permissions error", limit=3)
Results: Found 2 similar episodes with solutions
Apply: Use chmod before running exec commands
```

## Tips

- Use specific, technical terms for better results
- Search multiple times with different term combinations
- Check both recent and older episodes for different perspectives
- High-importance episodes often contain critical lessons
- Episode IDs provide traceability for future reference
