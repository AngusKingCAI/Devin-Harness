# Implementation Lessons Learned

## Registry Implementation (Phase 1)

### YAML Frontmatter Parsing
- Hand-rolled YAML frontmatter parser works well with PyYAML (spec preference)
- Split on `---` boundaries and parse YAML block with `yaml.safe_load()`
- Keep the rest as markdown body
- ~20 lines of code, zero additional dependencies

### Pydantic Model Design
- Handle Pydantic field name conflicts (e.g., "schema" conflicts with BaseModel) by renaming
- Use "schema_definition" instead of "schema" to avoid conflicts
- ContractRef "required" field should be `list[str]` (JSON schema format), not `bool`
- Handle schema vs schema_definition naming in frontmatter parsing

### Registry Loading
- Support both flat files (`name.md`) and directory layout (`name/AGENT.md`)
- User-scoped agents (`~/.config/devin/agents/`) override project-scoped on name collision
- Scan project agents directory first, then user agents directory
- Gracefully handle malformed profiles with try/except and warnings

### Sub-agent Profile Format
- YAML frontmatter with `---` delimiters
- Standard fields: `name`, `description`, `allowed-tools`, `max-nesting`
- Orchestrator-specific fields under `orchestrator:` namespace
- Markdown body contains the system prompt
- Profile paths can be used by both Devin CLI and Orchestrator

## Quality Standards

### Code Quality
- Follow spec exactly unless user directs otherwise
- Handle Windows-specific issues (Unicode encoding, path separators)
- Avoid Pydantic field name conflicts with parent classes
- Use proper error handling with informative messages

### Windows-Specific Considerations
- Handle Unicode encoding issues (avoid special Unicode characters in output)
- Use proper path separators (forward slashes work cross-platform)
- Test on Windows environment to catch platform-specific issues

## Future Implementation Notes

These lessons should be applied to future phases:
- Phase 2: State machine implementation
- Phase 3: Memory system implementation
- Phase 4: Hook scripts implementation
- Phase 5+: Advanced features

## Logging Implementation (Phase 1 Update)

### Logging Setup Applied
- Added comprehensive JSONL logging to `registry.py`
- Added logging to test file `test_registry.py`
- Created `.devin/logs/` directory for log files
- Log files: `{module_name}-Log.jsonl` in `.devin/logs/`
- Test documentation: `.devin/docs/orchestrator/tests/{timestamp}-{test_name}.md`

### Logging Configuration
- JSONL format for machine-readable logs
- Human-readable console output (INFO level and above)
- DEBUG level logs go to file only
- Timestamps in UTC with "Z" suffix
- Includes: timestamp, level, module, function, line, message, exception info

### Timezone Handling Fix
- Use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`
- Import `timezone` from datetime module
- Format with `.replace("+00:00", "Z")` for proper UTC suffix

### Windows-Specific Issues Fixed
- Removed Unicode characters from test output (checkmarks caused encoding errors)
- Use ASCII-safe characters: `[PASS]`, `[FAIL]`, `[SUCCESS]`
- File encoding specified as `utf-8` for cross-platform compatibility