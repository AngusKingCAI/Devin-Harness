# Orchestrator Project Structure

## Domain-based Organization

The Orchestrator uses domain-based grouping for better organization:

- **scripts/[domain]/** - Python files organized by domain
- **config/[domain]/** - JSON configuration files organized by domain
- **state/** - Runtime state files
- **memory/** - Archival memory files

## Current Directory Structure

```
.devin/
├── scripts/
│   ├── hooks/           # Hook scripts (Phase 4)
│   ├── memory/          # Memory operations (Phase 3)
│   │   ├── audit.py
│   │   ├── decisions.py
│   │   ├── memory.py
│   │   └── __init__.py
│   ├── orchestrator/    # Core orchestration (Phase 5)
│   ├── pipeline/        # Pipeline configuration (Phase 2)
│   │   └── pipeline.py
│   ├── registry/        # Registry management (Phase 1)
│   │   └── registry.py
│   └── state/           # State management (Phase 2)
│       ├── state.py
│       └── lock.py
├── config/
│   ├── hooks/           # Hook configurations
│   ├── memory/          # Memory-related configs
│   ├── orchestrator/    # Orchestrator-specific configs
│   ├── pipeline/        # pipeline.json (Phase 2)
│   │   └── pipeline.json
│   ├── registry/        # Registry-related configs
│   ├── state/           # State-related configs
│   └── policy.json      # General policy configuration
├── state/
│   ├── runs/            # Runtime scratch directories
│   └── escalations/     # Escalation files
├── memory/
│   └── archive/         # Completed run archives
├── agents/              # Sub-agent profiles (Phase 1)
│   └── dummy/
│       └── AGENT.md
├── tasks/               # Task prompt files (Phase 2)
│   └── dummy-task.md
├── logs/                # JSONL log files (Phase 1+)
│   ├── registry.registry-Log.jsonl
│   ├── pipeline.pipeline-Log.jsonl
│   ├── state.state-Log.jsonl
│   ├── state.lock-Log.jsonl
│   ├── test_registry-Log.jsonl
│   ├── test_pipeline-Log.jsonl
│   └── test_state-Log.jsonl
├── tests/               # Test files by domain
│   ├── pipeline/
│   │   └── test_pipeline.py
│   ├── registry/
│   │   └── test_registry.py
│   └── state/
│       └── test_state.py
└── hooks.v1.json        # Must be in .devin/ root (Phase 4)
```

## File Placement Decisions

- Python scripts go in `scripts/` by domain
- Configuration files go in `config/` by domain
- Runtime state files go in `state/` or `memory/` based on purpose
- hooks.v1.json must live directly in `.devin/` for Devin CLI to find it
- Always ask user for file locations rather than assuming structure
- Respect existing directory organization when possible

## Domain Responsibilities

**Registry Domain** - Managing sub-agent profiles (Phase 1)
- `scripts/registry/registry.py` - Registry implementation
- `config/registry/` - Registry-specific configurations
- `tests/registry/test_registry.py` - Registry tests

**Pipeline Domain** - Pipeline configuration and execution (Phase 2)
- `scripts/pipeline/pipeline.py` - Pipeline loader with JSON schema validation
- `config/pipeline/pipeline.json` - Pipeline definition
- `tests/pipeline/test_pipeline.py` - Pipeline tests

**State Domain** - State management (Phase 2)
- `scripts/state/state.py` - State machine and workflow state models
- `scripts/state/lock.py` - Orchestrator lock for process synchronization
- `config/state/` - State-related configurations
- `state/runs/` - Runtime scratch directories
- `state/escalations/` - Escalation files
- `tests/state/test_state.py` - State machine and lock tests

**Memory Domain** - Memory operations (Phase 3)
- `scripts/memory/audit.py` - Audit log with SHA-256 hash chain
- `scripts/memory/decisions.py` - SQLite FTS5 decision database
- `scripts/memory/memory.py` - Memory system facade
- `config/memory/` - Memory-related configurations
- `memory/archive/` - Completed run archives

**Orchestrator Core Domain** - Main coordination (Phase 5)
- `scripts/orchestrator/main.py` - Entry point
- `scripts/orchestrator/subprocess_runner.py` - Subprocess management
- `config/orchestrator/` - Orchestrator-specific configs

**Hooks Domain** - Hook scripts (Phase 4)
- `scripts/hooks/` - 8 hook scripts
- `config/hooks/` - Hook configurations
- `.devin/hooks.v1.json` - Main hook configuration (must be in .devin/ root)

**Tasks Domain** - Task prompt files (Phase 2)
- `tasks/` - Task prompt files for pipeline stages
- `tasks/dummy-task.md` - Example task for dummy stage

**Logs Domain** - JSONL logging (Phase 1+)
- `logs/` - JSONL log files for all modules
- Module-specific log files: `{module_name}-Log.jsonl`
- Test-specific log files: `test_{module_name}-Log.jsonl`