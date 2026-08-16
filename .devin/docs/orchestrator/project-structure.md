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
│   ├── hooks/           # Hook scripts
│   ├── memory/          # Memory operations (memory.py)
│   ├── orchestrator/    # Core orchestration (main.py, subprocess_runner.py, lock.py)
│   ├── pipeline/        # Pipeline configuration (pipeline.py)
│   ├── registry/        # Registry management (registry.py)
│   └── state/           # State management (state.py)
├── config/
│   ├── hooks/           # Hook configurations
│   ├── memory/          # Memory-related configs
│   ├── orchestrator/    # Orchestrator-specific configs
│   ├── pipeline/        # pipeline.json
│   ├── registry/        # Registry-related configs
│   ├── state/           # State-related configs
│   └── policy.json      # General policy configuration
├── state/
│   ├── runs/            # Runtime scratch directories
│   └── escalations/     # Escalation files
├── memory/
│   └── archive/         # Completed run archives
├── agents/              # Sub-agent profiles
└── hooks.v1.json        # Must be in .devin/ root
```

## File Placement Decisions

- Python scripts go in `scripts/` by domain
- Configuration files go in `config/` by domain
- Runtime state files go in `state/` or `memory/` based on purpose
- hooks.v1.json must live directly in `.devin/` for Devin CLI to find it
- Always ask user for file locations rather than assuming structure
- Respect existing directory organization when possible

## Domain Responsibilities

**Registry Domain** - Managing sub-agent profiles
- `scripts/registry/registry.py` - Registry implementation
- `config/registry/` - Registry-specific configurations

**Pipeline Domain** - Pipeline configuration and execution
- `scripts/pipeline/pipeline.py` - Pipeline loader
- `config/pipeline/pipeline.json` - Pipeline definition

**State Domain** - State management
- `scripts/state/state.py` - State machine implementation
- `config/state/` - State-related configurations
- `state/runs/` - Runtime scratch directories
- `state/escalations/` - Escalation files

**Memory Domain** - Memory operations
- `scripts/memory/memory.py` - Memory implementation
- `config/memory/` - Memory-related configurations
- `memory/archive/` - Completed run archives

**Orchestrator Core Domain** - Main coordination
- `scripts/orchestrator/main.py` - Entry point
- `scripts/orchestrator/subprocess_runner.py` - Subprocess management
- `scripts/orchestrator/lock.py` - Process locking
- `config/orchestrator/` - Orchestrator-specific configs

**Hooks Domain** - Hook scripts
- `scripts/hooks/` - 8 hook scripts
- `config/hooks/` - Hook configurations
- `.devin/hooks.v1.json` - Main hook configuration (must be in .devin/ root)