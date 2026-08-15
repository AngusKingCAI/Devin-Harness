---
triggers: ["user", "model"]
description: Save important lessons or facts to episodic memory
argument-hint: [content]
---

# Memory Save Skill

## Purpose
Save important information to episodic memory for future reference by agents.

## When to Use
- After solving a difficult problem
- When discovering a new pattern or approach
- After encountering an error that might recur
- When learning something that applies to multiple situations
- After completing a task with valuable insights

## Procedure

1. **Identify Key Learnings**: Extract the most important information
   - What was the core problem or insight?
   - What was the solution or approach?
   - Why is this important for future tasks?
   - What are the generalizable lessons?

2. **Format Content**: Create a concise, actionable memory entry
   - Keep it under 200 characters for optimal recall
   - Make it actionable (what to do, not just what happened)
   - Make it generalizable (applies to multiple situations)
   - Include specific technical details if relevant

3. **Save to Memory**: Use the MCP memory tool
   ```
   Call: mcp__memory__memory_save
   Parameters:
   - content: "<lesson learned>"
   - importance: "high" (for critical lessons) or "medium" (default)
   - event_type: "fix" (for solutions) or "note" (default)
   - agent: "<current agent name>"
   ```

## Content Guidelines

**Good Examples:**
- "Always check file permissions before running exec commands"
- "Researcher needs MANDATORY source verification enforcement"
- "Use FastMCP instead of Server class for MCP servers"
- "Temporal consistency check: reject sources dated after research date"

**Poor Examples:**
- "I fixed a bug" (too vague, not actionable)
- "The error was very long and hard to read" (not generalizable)
- "Use the right tool for the job" (too generic)

## Importance Levels

- **high**: Critical lessons that prevent major issues or enable important workflows
- **medium**: Useful patterns and insights that improve efficiency
- **low**: Minor observations or temporary notes

## Example Usage

**Scenario**: After solving MCP server integration issues

```
Lesson: "Use FastMCP from mcp.server.fastmcp instead of Server class for MCP servers"
Importance: high
Event type: fix
Agent: Orchestrator
```

## Tips

- Save lessons immediately after learning them while fresh
- Include context in the content (what, why, how)
- Reference specific file paths or patterns when relevant
- Use importance level appropriately to aid future retrieval
- Consider both technical and process lessons
