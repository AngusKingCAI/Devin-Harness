# Devin CLI Integration

## Web Search Guidelines

### When to Use Web Search
Use websearch for Devin CLI-specific issues:
- When encountering Devin CLI configuration problems
- When unsure about hook behavior or payload structure
- When dealing with version-specific Devin CLI features
- When implementing integrations with Devin CLI hooks or subagents

### Search Strategy
- Always include "devin cli" in search queries for relevant results
- Search should focus on docs.devin.ai and official Devin CLI documentation
- When unsure about a specific feature, search for "devin cli [feature name]"
- Cross-reference findings with the spec document
- If websearch doesn't resolve the issue, ask the user for direction

## Key Devin CLI Concepts

### Hook System
- Devin CLI has 8 hook events: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PermissionRequest, Stop, PostCompaction, SessionEnd
- Hooks are configured in `.devin/hooks.v1.json` (must be in .devin/ root)
- Hook scripts receive JSON payload on stdin and return JSON on stdout
- Exit code 2 blocks actions, exit code 0 allows actions

### Subagent Profiles
- Subagent profiles are markdown files in `.devin/agents/` or `~/.config/devin/agents/`
- Format: YAML frontmatter + markdown body
- Standard fields: name, description, allowed-tools, max-nesting
- Orchestrator-specific fields under "orchestrator:" namespace
- Support both flat files (name.md) and directory layout (name/AGENT.md)

### Version Requirements
- Minimum Devin CLI version: 3000.2.17 (for session_id/prompt_id in hook payloads)
- All sub-agents run on SWE-1.6 (Devin CLI's default subagent model)
- FTS5 must be available in SQLite (Python stdlib includes it)

## Configuration Files

### hooks.v1.json
- Must be located directly in `.devin/` directory
- Configures hook scripts for each event type
- Uses matcher patterns for tool-specific hooks
- Example structure:
```json
{
  "PreToolUse": [
    {
      "matcher": "exec",
      "hooks": [
        {"type": "command", "command": "python /path/to/hook.py", "timeout": 10}
      ]
    }
  ]
}
```

### config.json
- Devin CLI configuration file
- Can be in `.devin/` or user config directory
- Contains permission mode, model settings, etc.
- Orchestrator may need specific config for hook integration

## Common Integration Patterns

### Hook Script Communication
- Hooks read JSON from stdin
- Hooks return JSON on stdout or exit codes
- Use `hookSpecificOutput` for context injection
- Use `decision: block` for destructive commands (cancels whole turn)

### Subagent Invocation
- Use `devin -p --prompt-file <task>` for non-interactive execution
- Use `devin acp` for JSON-RPC streaming (advanced)
- Pass environment variables for orchestrator context
- Handle subprocess lifecycle and cleanup

### Error Handling
- Handle hook script failures gracefully
- Use retry policies for transient failures
- Log all hook events for audit trail
- Implement proper subprocess cleanup

## References

- Official Devin CLI docs: https://docs.devin.ai/cli/
- Hooks overview: https://docs.devin.ai/cli/extensibility/hooks/overview.md
- Subagents: https://docs.devin.ai/cli/subagents.md
- Configuration: https://docs.devin.ai/cli/extensibility/configuration.md