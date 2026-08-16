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

## Phase 2 Implementation (State Machine)

### State Machine Implementation
- Config-driven state machine derived from pipeline.json
- StateMachine.can_transition() validates transitions before applying
- StateMachine.transition() applies transitions and returns new state
- State does NOT write to disk - caller responsible for atomic_write_state()

### WorkflowState Model
- Pydantic v2 models for WorkflowState and StageStateRecord
- Support for all required fields from spec (heartbeat, idempotency_key, etc.)
- Validation method to ensure current_stage_id exists in stage_states

### Atomic Write Pattern
- Write-to-temp-then-rename with fsync for crash safety
- Works on POSIX with full fsync (file + directory)
- Windows: skip directory fsync due to permission issues (non-critical)
- Pattern: tempfile.mkstemp → write → fsync → os.replace → fsync(dir)

### OrchestratorLock Implementation
- File-based lock for process synchronization
- Windows: msvcrt.locking (primary) with fallback to file creation
- POSIX: fcntl.flock with blocking/non-blocking modes
- Context manager support for easy use

### Pipeline Configuration
- JSON schema validation using jsonschema library
- Pydantic models for StageConfig, StageInput, TerminalState
- Validation against spec schema before loading
- Stage lookup by ID and terminal state lookup

### Windows-Specific Issues Fixed
- Permission denied on directory fsync - skip on Windows
- Lock implementation has Windows fallback without msvcrt
- ASCII-safe test output maintained

### Type Checking
- Used TYPE_CHECKING for PipelineConfig import to avoid circular imports
- Made atomic_write_state accept Any type for flexibility

## Testing Limitations (Phase 2)

### What We Actually Tested
- Unit tests for PipelineConfig.load() with temporary JSON files
- Unit tests for StateMachine.transition() with mock pipeline config
- Unit tests for atomic_write_state() in temp directories
- Unit tests for OrchestratorLock in temp directories
- Integration test with real project pipeline.json
- Simulated crash recovery (script exit before rename)
- Simulated lock contention (two Python processes)

### What We Did NOT Test (Real-World Scenarios)
- **Real process termination**: We did not actually kill a process mid-write with taskkill/SIGKILL
- **Power failure simulation**: Cannot test real power failure scenarios
- **Real concurrent lock competition**: Used Python scripts instead of real competing processes
- **Windows-specific atomic rename edge cases**: Did not test cross-volume renames
- **Real production load**: No testing under load or stress conditions

### Limitations
- Crash recovery test was simulated with script exit, not real process kill
- Lock contention test used coordinated Python scripts, not real competing processes
- Tests used temporary directories, not actual project paths for most tests
- No testing of concurrent access to workflow-state.json in production-like scenarios

### Assessment
The atomic write pattern we implemented follows the established best practices (temp file + fsync + atomic rename), but we have not verified it against real crash scenarios. The lock implementation uses standard patterns but has not been tested against real concurrent process competition in production.

### Lock Contention Test Issues
The lock contention test initially failed due to timing issues - the first attempt allowed both processes to acquire the lock because the contender didn't wait long enough for the holder to establish the lock. Only after adjusting timing (holder holds for 3 seconds, contender waits 0.5 seconds, main process waits 1 second) did the test pass. This reveals that:
- Simple file-based locks (os.O_CREAT | os.O_EXCL) work but depend on precise timing
- Real-world concurrent access could still have race conditions we haven't caught
- Our testing is not robust against timing variations

## Phase 3 Implementation (Memory System)

### Audit Log System
- SHA-256 hash chain for integrity verification
- append_audit() with prev_hash chain linking
- verify_audit_chain() walks log and recomputes hashes
- Tamper detection raises ValueError with specific line number
- JSONL format for append-only audit trail

### Decision Database
- SQLite with FTS5 full-text search
- verify_fts5() probes FTS5 availability at startup
- Schema with decisions, decisions_fts, shared_facts, shared_facts_fts tables
- Triggers to keep FTS5 tables in sync with main tables
- WAL mode for crash safety
- BM25 ranking for search results

### Memory System Facade
- MemorySystem class combining audit log and decision database
- Context manager support for automatic cleanup
- Unified API for audit events, decisions, and shared facts
- Integrated initialization and verification

### Windows-Specific Issues
- WAL mode only works with file-based databases, not :memory:
- Changed test to use temp file instead of in-memory database for WAL verification

### Testing Limitations
- Module split followed best practices from web search
- Tests use temporary directories, not production paths
- No testing of concurrent database access
- No testing of database recovery from corruption

## Future Implementation Notes

These lessons should be applied to future phases:
- Phase 4: Hook scripts implementation
- Phase 5: Orchestrator main loop and subprocess runner
- Phase 6+: Advanced features

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