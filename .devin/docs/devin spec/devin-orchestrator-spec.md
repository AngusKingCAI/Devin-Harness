# Devin CLI Orchestrator & Dynamic Sub-Agent Harness — Implementation Specification

**Document type:** Build specification for Devin CLI (the implementer)
**Spec version:** 1.0
**Date:** 2026-08-16
**Spec posture:** The brief's 8-hook event list and 0/2/other exit-code convention are the authoritative TARGET spec. They have been verified against Devin CLI's own primary-source documentation (see Section 2 and Section 12). Where the brief's terminology diverges from Devin CLI's actual API (e.g., `modifiedInput` vs `updatedInput`, `permissionDecision` vs `decision`), this spec uses Devin CLI's actual terminology and flags the divergence in Section 11.
**Model policy:** All sub-agents run on Devin CLI's default subagent model (SWE-1.6). Model switching is out of scope. The `model` frontmatter field and the `--model` CLI flag are intentionally omitted from this spec (see Section 11.14).
**Sourcing rule:** Only Devin CLI's own docs (docs.devin.ai) are cited as authoritative for hook payloads and semantics. Where Devin's docs themselves cross-reference Claude Code's format (and they do — Devin explicitly states its hooks are "the same convention used by Claude Code, Cursor, and other tools"), that cross-reference is preserved as Devin's own statement, not as an independent citation of Claude Code docs.

---

## Table of Contents

1. Executive Summary
2. Verified Devin CLI Hook System
3. Sub-Agent Registry Design
4. Enforcement Model: Blocking vs. Non-Blocking
5. Memory Stack Specification
6. State Machine Specification
7. Hook Integration Map
8. Inter-Agent Handoff Contracts
9. Error Handling & Recovery
10. Phased Build Plan
11. Open Questions & Risks
12. Sources

---

## 1. Executive Summary

### 1.1 The problem this harness solves

A single Devin CLI coding session, run ad hoc against a complex task, loses state mid-task in two distinct ways:

1. **Context compaction.** When the session's token budget fills, Devin CLI compacts the conversation. Without an external recovery brief, post-compaction the agent has lost the workflow's shape — what stage it was in, what prior stages decided, what the next handoff requires. It may continue, but it continues *amnesiac*.
2. **Crash.** If the Devin CLI process dies — power loss, OOM kill, accidental terminal close, a buggy hook script — the in-memory conversation is gone. Restarting means re-deriving the entire workflow from scratch.

Both failure modes are catastrophic for multi-step workflows (research → plan → implement → review → execute) that take hours of agent work to produce. The harness this spec describes exists to make those workflows resumable.

### 1.2 The harness, in one paragraph

The **Orchestrator** is a single local Python 3.11 async process that owns a pipeline of sub-agent invocations. Sub-agents are not hardcoded — they are defined as **markdown profile files** in a directory the Orchestrator scans at startup (and may hot-reload). The pipeline's sequence is itself data: a top-level `pipeline.json` (or `pipeline.yaml`) references sub-agent profiles by name and declares their order. The Orchestrator persists three things to disk: `workflow-state.json` (the live state of the current pipeline run), `action-log.jsonl` (an append-only, hash-chained audit trail of every event the Orchestrator and its hooks observe), and `decisions.sqlite` (a SQLite database with FTS5 full-text search over every decision any sub-agent has made, queryable by any future sub-agent). At every hook event Devin CLI fires, the Orchestrator's hook script reads the appropriate memory layer, writes the appropriate memory layer, and returns either a `decision`, an `additionalContext` injection, an `updatedInput` rewrite, or nothing — per a single, consistent enforcement policy (Section 4). When Devin CLI compacts mid-stage, the `PostCompaction` hook fires and the Orchestrator rebuilds a recovery brief from disk and re-injects it on the next `UserPromptSubmit` (the documented re-injection channel — see Section 2.6 for why `PostCompaction` itself cannot inject). When the Orchestrator process crashes, on restart it reads `workflow-state.json`, determines which stage was in flight, and either resumes that stage (if its output was complete on disk) or restarts it (if not). Adding a sixth sub-agent, reordering the pipeline, or running an entirely different pipeline is a config-file edit — zero code changes.

### 1.3 Key design decisions, each with a one-line justification

| # | Decision | Justification (one line) |
|---|---|---|
| 1 | **Sub-agents are Devin CLI native subagent profiles** (`.devin/agents/<name>.md`), and the registry IS that directory — no separate registry format. | Devin CLI already auto-discovers these files; building a parallel registry would duplicate a working native mechanism and force a mapping layer. (Section 3) |
| 2 | **The pipeline is a separate `pipeline.json`** that references sub-agent profiles by name and declares their order and branch conditions. | The native subagent format has no concept of "pipeline position" — that's an Orchestrator concern, so it lives in an Orchestrator-owned file. (Section 3) |
| 3 | **Working memory = `workflow-state.json`** (atomic write via temp + fsync + `os.replace` + fsync dir). | Single-file, human-readable, atomic-replace is the canonical crash-safe pattern; validated by DeerFlow's `memory.json` and Hermes's snapshot pattern. (Section 5) |
| 4 | **Episodic memory = `action-log.jsonl`** (append-only, O_APPEND + single write + fsync per record, SHA-256 hash chain for tamper-evidence). | Append-only JSONL is the standard audit-log format; hash-chaining detects in-place tampering by same-user processes, which is the actual threat model. (Section 5) |
| 5 | **Semantic memory = `decisions.sqlite` with FTS5 + BM25** (external-content table + triggers, WAL mode, `synchronous=FULL`). | FTS5 keyword search with BM25 ranking is zero-dependency (Python stdlib), runs in <30 ms per query in production (OpenClaw, Hermes, DeerFlow all use it), and is sufficient for natural-language decision retrieval without an embedding model. (Section 5) |
| 6 | **Shared/blackboard memory = `workflow-state.json`'s `shared_context` field** + a `shared_facts` table in `decisions.sqlite`. | The harness does not need a separate blackboard system; the existing working-memory file and the existing semantic-memory DB cover both "live shared state" and "queryable shared facts" without a new storage layer. (Section 5) |
| 7 | **Procedural memory = the sub-agent profile markdown body** (each profile's system prompt) + a project-level `AGENTS.md`. | Procedural rules belong in prompts, not in the memory store — this is the cross-tool convention (Claude Code `CLAUDE.md`, Hermes `MEMORY.md`, Cursor rules, Devin `AGENTS.md`). (Section 5) |
| 8 | **Compaction policy: only between stages, ~120K-token trigger, recovery brief re-injected via `UserPromptSubmit` hook.** | The brief requires between-stage compaction; `UserPromptSubmit` is the documented channel for context injection that survives compaction (PostCompaction cannot inject — Section 2.6). |
| 9 | **Enforcement: hard-block (`exit 2` or `decision:block`) ONLY on `PreToolUse` for unambiguously destructive commands; everything else is audit + `additionalContext` injection.** | Devin CLI's `decision:block` cancels the whole agent turn (not just the one tool call) — using it for soft corrections would abort the workflow. `Stop` hooks that always block cause infinite loops (documented). (Section 4) |
| 10 | **State machine is hand-rolled Pydantic v2 + config-driven transition table** (no `transitions` library — it doesn't compose with Pydantic v2). | ~20 lines of code, no dependency, fully config-driven so adding a stage requires zero state-machine code changes. (Section 6) |
| 11 | **Subprocess invocation: `asyncio.create_subprocess_exec` with `start_new_session=True`** + explicit `os.killpg` on timeout/cancellation. | The documented KISS pattern for spawning a CLI binary with proper cleanup; `start_new_session=True` makes `killpg` reach all descendant processes. (Section 9) |
| 12 | **Liveness: heartbeat file (every 30s) + stdout inactivity timeout (300s) + hard wall-clock cap (1h, configurable per stage).** | Belt-and-suspenders against both "agent silently hung" and "agent legitimately working but slow"; mirrors LangGraph's `TimeoutPolicy` pattern. (Section 9) |

### 1.4 What this spec is NOT

- **Not a framework.** No plugin abstraction layer, no hookspec/hookimpl registry, no dynamic code loading. Sub-agents are data files; the Orchestrator's logic is fixed.
- **Not distributed.** Single machine, single Python process, single SQLite file. No Kafka, Redis, Kubernetes, Postgres, vector DB, or embedding model.
- **Not a Claude Code harness.** Devin CLI's hooks are Claude-Code-format-compatible but are Devin's own 8-event subset (Claude Code has 31). The spec uses Devin's actual field names (`updatedInput`, `decision:approve|block`) and Devin's actual CLI flags (`-p`/`--print`, not `--output-format json`). See Section 2.10 for the divergence list.

### 1.5 Reading order for the implementer

Read Section 2 first (to ground every later decision in Devin CLI's actual API), then Section 3 (the registry shapes Sections 5–8), then Sections 5–7 together (memory, state, hooks are interlocking), then Sections 8–9 (handoff and recovery build on the prior three), then Section 10 (the literal build checklist). Section 11 lists every judgment call this spec made on the user's behalf — read it before assuming any "obvious" choice.

---

## 2. Verified Devin CLI Hook System

**Verification status: VERIFIED against primary sources.**
**Primary sources (all accessed 2026-08-16):**
- Hooks overview: `https://docs.devin.ai/cli/extensibility/hooks/overview.md`
- Lifecycle hooks deep-dive: `https://docs.devin.ai/cli/extensibility/hooks/lifecycle-hooks.md`
- CLI command reference: `https://docs.devin.ai/cli/reference/commands.md`
- Extensibility overview: `https://docs.devin.ai/cli/extensibility/index.md`
- Configuration: `https://docs.devin.ai/cli/extensibility/configuration.md`
- Subagents: `https://docs.devin.ai/cli/subagents.md`
- Changelog: `https://docs.devin.ai/cli/changelog/stable.md`

**Independent community corroboration (all accessed 2026-08-16):**
- `oraios/serena#1757` — Serena's Devin CLI integration PR; empirically verified the payload schema and the `decision:block` whole-turn-scope caveat against `devin 3000.2.17`.
- `rtk-ai/rtk#3143` — RTK Devin integration feature request; confirms hook shape matches Claude Code/Cursor.
- `paperclipai/paperclip#11109` — adapter request confirming headless mode and structured output parsing.
- `TheColliery/CoalHearth` — ships a real `.devin/hooks.v1.json` example.

### 2.1 The 8 hook events — confirmed

Devin CLI documents exactly 8 hook events. The brief's list is correct. The table below is reconstructed verbatim from `lifecycle-hooks.md` (accessed 2026-08-16).

| # | Event | When it fires | Stdin payload (in addition to the common fields in §2.2) | May return |
|---|---|---|---|---|
| 1 | `SessionStart` | When a session begins | `source` (how the session was started) | `hookSpecificOutput.additionalContext` |
| 2 | `UserPromptSubmit` | When the user submits a message | `prompt` (the user's message text) | `hookSpecificOutput.additionalContext` |
| 3 | `PreToolUse` | Before a tool executes | `tool_name`; `tool_input` | `decision: approve\|block` + `reason`; OR `hookSpecificOutput.updatedInput` (merged into tool args before execution); OR exit code 2 |
| 4 | `PostToolUse` | After a tool finishes executing | `tool_name`; `tool_input`; `tool_response` (object with `success:boolean`, `output:string`, `error:string\|null`) | `hookSpecificOutput.additionalContext` |
| 5 | `PermissionRequest` | When a permission decision is needed | `tool_name`; `tool_input` | `decision: approve\|block` (+ optional `reason`) |
| 6 | `Stop` | When the agent decides to stop (finish its turn) | `stop_hook_active` (boolean) | `{"decision":"block","reason":"..."}` — **WARNING:** blocking Stop can cause infinite loops if the block condition is never satisfied |
| 7 | `PostCompaction` | After context compaction completes **successfully** | `summary` (the compaction summary text; may be null) | Logging only — **see §2.6 for why additionalContext cannot be returned here** |
| 8 | `SessionEnd` | When a session ends | `reason` (why the session ended) | Logging/cleanup only |

### 2.2 Common payload fields — every hook receives these

From `overview.md` (accessed 2026-08-16), every hook's stdin payload carries:

| Field | Type | Semantics |
|---|---|---|
| `hook_event_name` | string | The event name (e.g., `"PreToolUse"`). Redundant with the configured event key but always present. |
| `session_id` | string (UUID) | **Stable per session.** Same value across every hook invocation in one session. Confirmed usable as the audit-log correlation key. |
| `prompt_id` | string (UUID) | **Per-turn id, rotated on every user prompt.** All hooks fired during the same turn share one `prompt_id`. **ABSENT for `SessionStart`** (it fires before the first user prompt). Confirmed usable as the per-turn correlation key. |
| `DEVIN_PROJECT_DIR` | env var (not stdin) | Auto-set to the project root. Use this instead of a `cwd` field — Devin CLI does NOT put `cwd` in the payload. |

**Example stdin payload (verbatim from `overview.md`):**
```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "exec",
  "tool_input": {"command": "rm -rf /"},
  "session_id": "3f8d1c2a-...",
  "prompt_id": "b71e9d40-..."
}
```

**Minimum-version pin:** `session_id` and `prompt_id` arrived in Devin CLI v3000.2.17 (July 19, 2026). Earlier versions did NOT expose them. The harness's `pyproject.toml` / install instructions must pin `devin >= 3000.2.17`. (Source: `changelog/stable.md`, accessed 2026-08-16.)

### 2.3 Exit code semantics — confirmed

From `overview.md` (accessed 2026-08-16):

| Exit code | Meaning |
|---|---|
| `0` | Success — hook completes normally, action proceeds. |
| `2` | Block — action is denied. |
| Any other | Error — logged by Devin CLI but does NOT block. |

### 2.4 JSON-on-stdout output convention — confirmed, with corrections to the brief

The brief states: *"A `{"decision": "block", "reason": "..."}` response on stdout does the same thing more expressively."* This is **partially correct**. The full set of recognized JSON output fields, verified from `overview.md`:

#### 2.4.1 Top-level `decision` field

```json
{"decision": "block", "reason": "Destructive command blocked by policy"}
```

- `decision`: `"approve"` or `"block"` — **only these two values.** NOT `"allow"`, `"deny"`, or `"ask"` (those are Claude Code's `permissionDecision` vocabulary — Devin does NOT use them).
- `reason`: optional human-readable string.
- Scope: **a top-level `decision: block` cancels the ENTIRE agent turn** in Devin CLI (empirically verified by `oraios/serena#1757` against `devin 3000.2.17`). This is a critical behavioral difference from Claude Code, where `PreToolUse` returning `deny` rejects only the single tool call and lets the agent continue. **Consequence: do NOT use `decision: block` for "nudge the agent to try a different approach" semantics — it will abort the whole turn.** For nudging, use `hookSpecificOutput.updatedInput` to rewrite the tool call to a no-op (Section 4).

#### 2.4.2 `hookSpecificOutput` — the actually-more-expressive outputs

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "updatedInput": {"command": "echo 'blocked: original command was destructive'"}
  }
}
```

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "Recovery brief: you are in stage 'implementor'. Prior decisions: ..."
  }
}
```

- `hookSpecificOutput.hookEventName`: string, must match the event the hook was registered for.
- `hookSpecificOutput.updatedInput`: object, **valid ONLY for `PreToolUse`**. Merged into the tool's arguments before execution. Use this to rewrite a destructive command to a safe one (or a no-op) instead of blocking.
- `hookSpecificOutput.additionalContext`: text, **valid for `UserPromptSubmit`, `SessionStart`, `PostToolUse` ONLY.** Injected into the agent's context. **NOT valid for `PostCompaction`** despite the brief's implication — see §2.6.

#### 2.4.3 Fields the brief mentions that Devin CLI does NOT document

The brief implies the following fields exist; **Devin CLI's docs do NOT document them**. They appear to be Claude Code conventions. The harness must NOT rely on them:

| Brief's field | Devin CLI's actual equivalent |
|---|---|
| `permissionDecision: "allow"/"deny"/"ask"` | `decision: "approve"/"block"` (only two values; `"ask"` is implicit when a `PermissionRequest` hook returns no decision) |
| `modifiedInput` | `hookSpecificOutput.updatedInput` |
| `additionalContext` (as a top-level field) | `hookSpecificOutput.additionalContext` (must be nested) |
| `cwd` (in stdin payload) | `DEVIN_PROJECT_DIR` env var |
| `transcript_path` (in stdin payload) | Not provided by Devin CLI |

### 2.5 How hooks are registered — config schema

**Standalone file (recommended):** `.devin/hooks.v1.json` — the hooks object IS the entire file (no wrapper key):

```json
{
  "PreToolUse": [
    {
      "matcher": "exec",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/pre_tool_use.py", "timeout": 10}
      ]
    }
  ],
  "PostToolUse": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/post_tool_use.py", "timeout": 10}
      ]
    }
  ],
  "UserPromptSubmit": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/user_prompt_submit.py", "timeout": 10}
      ]
    }
  ],
  "SessionStart": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/session_start.py", "timeout": 10}
      ]
    }
  ],
  "SessionEnd": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/session_end.py", "timeout": 10}
      ]
    }
  ],
  "PermissionRequest": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/permission_request.py", "timeout": 10}
      ]
    }
  ],
  "Stop": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/stop.py", "timeout": 10}
      ]
    }
  ],
  "PostCompaction": [
    {
      "matcher": "",
      "hooks": [
        {"type": "command", "command": "python /path/to/orchestrator/hooks/post_compaction.py", "timeout": 10}
      ]
    }
  ]
}
```

**Alternative: under a `"hooks"` key** in any of these config files (per `overview.md`'s "Where Hooks Live" table):
- Project: `.devin/config.json`, `.devin/config.local.json`, `.claude/settings.json`, `.claude/settings.local.json`
- User (global): `~/.config/devin/config.json` (Linux/macOS), `%APPDATA%\devin\config.json` (Windows), `~/.claude.json`, `~/.claude/settings.json`, `~/.claude/settings.local.json`

**Per-hook fields:**

| Field | Description |
|---|---|
| `matcher` | **Regex** matched against `tool_name`. Empty string or omitted = match all. Only meaningful for `PreToolUse`, `PostToolUse`, `PermissionRequest`. For non-tool events, use `""` or omit. **Note: matcher is a regex, NOT a glob** — use `mcp__github__.*` not `mcp__github__*`. |
| `type` | `"command"` (shell command) or `"prompt"` (LLM prompt — Devin runs an LLM against the prompt and uses its output) |
| `command` | Shell command for `command` type. Receives the JSON payload on stdin. |
| `prompt` | LLM prompt for `prompt` type. |
| `timeout` | Optional, seconds. |

**Hook file discovery:** Project-level hook files are discovered in the working directory AND ancestor directories up to the repository root (added v3000.2.17, July 19, 2026). Hooks are deduplicated by source file (added same release).

**Verification command:** The `/hooks` slash command inside an interactive Devin CLI session lists all loaded hooks with their IDs, event types, and source paths.

**Import compatibility:** Hooks from `.claude/` paths are loaded when `read_config_from.claude` is enabled (default = enabled). Devin's docs explicitly state the hook format is Claude-Code-compatible. Changelog v2026.4.1-0 (April 1, 2026): *"Added support for reading hooks from `.devin/hooks.v1.json`, a standalone hooks file using the same format as Claude Code hooks."*

### 2.6 The PostCompaction re-injection caveat — CRITICAL

The brief states: *"a `PostCompaction` hook reloads state from disk and re-injects a recovery brief."* This is **half-right**. The `PostCompaction` hook fires (verified) and receives the compaction `summary` on stdin. But:

- Devin CLI's `overview.md` lists `hookSpecificOutput.additionalContext` as a valid return field for **`UserPromptSubmit`, `SessionStart`, and `PostToolUse` ONLY.**
- `PostCompaction` is **NOT in that list.**
- We could not verify from the official docs that `additionalContext` returned from a `PostCompaction` hook is honored by Devin CLI.

**The harness MUST therefore re-inject the recovery brief via the NEXT `UserPromptSubmit` hook, not via `PostCompaction`.** The `PostCompaction` hook's job is to (a) log the compaction event to `action-log.jsonl`, (b) set a flag in `workflow-state.json` indicating "compaction just happened, recovery brief needed on next prompt," and (c) optionally persist the compaction summary to `decisions.sqlite` for later retrieval. The actual re-injection happens on the next `UserPromptSubmit` (or `SessionStart` if the session was restarted), which reads the flag, builds the brief from disk, and returns it as `hookSpecificOutput.additionalContext`.

This is recorded as a Section 11 risk (MEDIUM) because it depends on Devin CLI firing `UserPromptSubmit` after compaction, which the docs do not explicitly guarantee.

### 2.7 Headless / non-interactive invocation — confirmed, with corrections to the brief

**The mechanism is `devin -p` / `--print`** — NOT a `--headless` flag (which does not exist). Verified from `https://docs.devin.ai/cli/reference/commands.md` (accessed 2026-08-16).

#### 2.7.1 Canonical non-interactive invocations

```bash
# Pass an initial prompt non-interactively, print response to stdout, exit
devin -p "list all TODO comments"

# Same via separator (useful when the prompt contains leading dashes)
devin -p -- list all TODO comments

# With permission mode pre-set
devin --permission-mode accept-edits -p "fix the failing tests"

# Sandbox-enforced autonomous run (macOS seatbelt / Linux bwrap+seccomp)
devin --sandbox -p "run the migration script"

# Load initial prompt from a file
devin --prompt-file task.md

# Resume a prior session non-interactively
devin -r <SESSION_ID> -p "continue"
devin -c -p "continue"   # continue most recent session in cwd

# Export conversation (ATIF format) for downstream parsing
devin --export out.json -p "fix the tests"

# Skip workspace trust prompt in CI
devin --respect-workspace-trust false -p "fix tests"

# Use a specific config file
devin --config /path/to/.devin/config.json -p "fix tests"
```

#### 2.7.2 Documented global flags (verbatim from `devin [OPTIONS] [prompt]`)

| Flag | Env var | Purpose |
|---|---|---|
| `--permission-mode <MODE>` | `DEVIN_PERMISSION_MODE` | One of `normal\|auto\|accept-edits\|smart\|dangerous\|yolo\|bypass\|autonomous`. |
| `--sandbox` | `DEVIN_SANDBOX` | macOS seatbelt / Linux bwrap+seccomp sandbox. |
| `--continue` / `-c` | — | Resume most recent session in cwd. |
| `--resume <SESSION_ID>` / `-r` | — | Resume a specific session. |
| `--print [PROMPT]` / `-p` | — | Non-interactive: print response and exit. Accepts optional inline prompt (changed v2026.4.1-0, April 1, 2026). |
| `--prompt-file <FILE>` | — | Load initial prompt from a file. |
| `--config <PATH>` | — | Use a specific config file. |
| `--export [PATH]` | — | Export conversation to ATIF format after each turn. |
| `--respect-workspace-trust [true\|false]` | — | Skip workspace trust prompt in CI. |

#### 2.7.3 Brief's flag list — verification

| Brief's flag | Devin CLI has it? |
|---|---|
| `--print` | ✅ YES (`-p` / `--print`) |
| `--output-format json` | ❌ NO. Claude Code has this; Devin CLI does not. Use `--export [PATH]` for ATIF-format conversation export, OR `devin acp` for JSON-RPC streaming. |
| `--agent <name>` | ❌ NO. Devin CLI does not let you pick a subagent at startup. Subagents are chosen at runtime by the parent agent via its `run_subagent` tool. To force a specific profile: define it in `.devin/agents/<name>.md` and instruct the parent in the prompt to use that profile. |
| `--initial-prompt` | ❌ NO. Use positional prompt, `-p "..."`, or `--prompt-file <FILE>`. |
| `--no-input` | ❌ NO. `-p` mode is inherently non-interactive; no separate flag. |
| `--headless` | ❌ NO. The mode is `-p` / `--print`. |
| `--max-turns` | ❌ NO. Not documented. The harness must enforce its own turn cap via the `Stop` hook or a wall-clock timeout. |

#### 2.7.4 Extracting structured output

Three options, in increasing order of richness:

1. **`-p` + stdout capture** — the simplest. The Orchestrator spawns `devin -p "..."`, captures stdout, parses the agent's final response as text. Adequate for stages whose output contract is "produce a markdown file at path X" (the Orchestrator reads the file, not stdout).
2. **`--export <PATH>`** — exports the full conversation in ATIF format after each turn. The Orchestrator parses ATIF to extract structured turn data. Use this when you need per-turn tool-call records.
3. **`devin acp`** — runs Devin as an Agent Client Protocol (ACP) JSON-RPC server over stdio. This is the closest equivalent to Claude Code's `--output-format stream-json` and is the recommended path for production-grade orchestration. The Orchestrator speaks ACP to Devin, receives structured events (tool calls, responses, stop signals) as JSON-RPC messages, and can interrupt or steer the session mid-flight. Documented at `https://docs.devin.ai/cli/reference/commands.md` (accessed 2026-08-16).

**Recommendation for the harness:** Start with option 1 (`-p` + stdout) for Phases 1–4 of the build plan (Section 10). Migrate to option 3 (`devin acp`) in Phase 5 once the basic pipeline is stable. Option 2 (`--export`) is a fallback if ACP proves unstable.

### 2.8 Concurrency limits — partially verified

**Could not find a documented "max concurrent sessions per user" ceiling.** Specifics:

- Multiple concurrent Devin CLI processes on one machine are explicitly supported. Cognition's launch blog (accessed 2026-08-16): *"Run multiple agents against the same codebase without fiddling with worktrees or setup scripts."*
- **Background shells are capped at 16 with LRU eviction** (changelog v3000.2.17, July 19, 2026): *"deliberately retained shells (explicit shell_id, tty, or backgrounded commands) are capped at 16 with least-recently-used eviction."*
- **Subagent nesting: `max-nesting` is a per-subagent frontmatter field** (verified in `subagents.md`). Default: subagents cannot spawn their own subagents (only the root agent can). A custom profile can opt in via `max-nesting: 3` (Root → Custom → Child → Grandchild, depth 3). Added v2026.5.26-0 (May 26, 2026).
- **Background subagents:** inherit pre-approved tool permissions only; any unpre-approved tool is auto-denied. Foreground subagents block the parent; background subagents parallelize. No documented hard ceiling on concurrent background subagents.
- **Organization policy** can disable subagents entirely via the enterprise "Default subagent model" setting (option "None").

**Consequence for the harness:** The Orchestrator MUST enforce its own concurrency ceiling (e.g., an `asyncio.Semaphore` with a configurable max, default 4 concurrent sub-agent sessions). Do NOT rely on Devin CLI to throttle. This is recorded as Section 11 risk (MEDIUM).

### 2.9 Where hooks fit in Devin CLI's overall extensibility model

From `https://docs.devin.ai/cli/extensibility/index.md` (accessed 2026-08-16), Devin CLI's extensibility stack, in increasing capability granularity:

1. **Rules & AGENTS.md** — always-on context (project-level `AGENTS.md`/`AGENT.md`/`CLAUDE.md`, or `.devin/...` rules). Imported from `.cursor/rules/`, `.windsurf/rules/`.
2. **Skills** — reusable prompts/workflows invokable as slash commands or autonomously. `SKILL.md` files in `.devin/skills/<name>/SKILL.md`.
3. **Plugins** — bundles of skills/rules/hooks/MCP servers/subagents shipped from a GitHub repo, git URL, or local path. `devin plugins install <source>`.
4. **Custom Subagents** — markdown profiles in `.devin/agents/<name>.md` (or `~/.config/devin/agents/`). **This is what the registry builds on (Section 3).**
5. **MCP Servers** — external tool servers via Model Context Protocol. Configured in `.devin/mcp_config.json`.
6. **Hooks** — shell commands / LLM prompts run at lifecycle events. **The integration layer the Orchestrator uses (this section).**
7. **Configuration** — JSON config at user and project levels.
8. **Slash commands** — interactive commands (`/hooks`, `/mcp`, `/mode`, `/compact`, etc.).
9. **ACP server** — `devin acp` exposes Devin as a JSON-RPC server over stdio.

**Where the Orchestrator plugs in:** Hooks (for lifecycle integration) + Custom Subagents (for the registry) + AGENTS.md (for procedural memory). It does NOT need Skills, Plugins, MCP Servers, or slash commands for the core harness — those are optional extensions.

### 2.10 Critical caveat: `decision: block` scope

**This is the single most important behavioral nuance for the enforcement model (Section 4).**

Empirically verified by `oraios/serena#1757` (accessed 2026-08-16) against `devin 3000.2.17`:

> *"In Devin CLI a top-level `{"decision":"block"}` cancels the agent's turn (unlike Claude Code's PreToolUse `deny`, which rejects the one call and lets the agent continue), so it is unusable for a nudge."*

The official Devin docs do NOT explicitly state the scope of `decision: block`. The Serena team's empirical finding is that it cancels the WHOLE turn, not just the single tool call.

**Consequence:** A `PreToolUse` hook that returns `decision: block` on a destructive command will abort the entire sub-agent's turn — which, depending on the state machine's design, may either restart the stage (with the same destructive impulse) or fail the stage entirely. The enforcement policy in Section 4 is designed around this: hard-block is reserved for commands so destructive that aborting the turn is the desired behavior; for everything else, the hook uses `hookSpecificOutput.updatedInput` to rewrite the call (which lets the agent continue) or `additionalContext` to inject a correction (which lets the agent self-correct).

### 2.11 Devin Desktop (Cascade Hooks) is a SEPARATE product — do not confuse

Devin Desktop (ex-Windsurf, ex-Codeium) is a different product with a different hook system called **Cascade Hooks** (documented at `https://docs.devin.ai/desktop/cascade/hooks.md`, accessed 2026-08-16). Cascade Hooks use snake_case event names (`pre_read_code`, `post_write_code`, `post_cascade_response`, `post_cascade_response_with_transcript`) and a different config schema (`.windsurf/hooks.json`).

**The harness is built around Devin CLI (`.devin/hooks.v1.json`, PascalCase events). Do NOT confuse the two.** The Cascade Hooks doc explicitly states: *"The hooks described here are Cascade hooks. The Devin Local agent has its own lifecycle hooks with a different configuration format."*

---

## 3. Sub-Agent Registry Design

**Resolution to Must-Resolve Question 1.**

### 3.1 The recommendation, in one paragraph

**The registry IS Devin CLI's native subagent profile directory.** A registry entry IS a `.devin/agents/<name>.md` markdown file with YAML frontmatter. The Orchestrator scans this directory at startup, parses each profile, and builds its in-memory registry by reading the frontmatter (sub-agent identifier, tool restrictions, max-nesting) and the markdown body (the system-prompt pointer — the body itself is the prompt). The pipeline's sequence — which sub-agents run, in what order, with what handoff conditions — is a SEPARATE Orchestrator-owned file, `pipeline.json`, that references sub-agent profiles by name. Adding a sixth sub-agent or reordering the pipeline requires editing `pipeline.json` (or dropping a new `.md` file in `.devin/agents/`); it requires ZERO code changes to the Orchestrator.

**Model policy:** All sub-agents run on SWE-1.6 (Devin CLI's default subagent model). The `model` frontmatter field is intentionally not used — see Section 11.14.

### 3.2 Why build on Devin CLI's native subagent profiles (vs. a separate registry format)

The brief asks: *"Evaluate whether the Orchestrator should build its registry directly on top of this (a registry entry IS a custom subagent profile file, invoked via Devin's subagent tool) versus maintaining an entirely separate registry format that maps to independent `devin` CLI session invocations. Recommend one, or a clear mapping between the two, with reasoning."*

**Recommendation: build on Devin CLI's native subagent profiles. A registry entry IS a `.devin/agents/<name>.md` file.**

Reasoning:

1. **Devin CLI's native mechanism is exactly the pattern the brief asks for.** Markdown files in a directory, auto-discovered, zero code changes to add a sub-agent. Verified in Section 2.9 and corroborated by Claude Code (the format's originator), Cursor, and Windsurf. Devin's own docs (`docs.devin.ai/cli/subagents.md`, accessed 2026-08-16) explicitly state: *"Custom subagents are defined as markdown files under `agents/`, using either layout: Flat file — `agents/<name>.md` (the same convention used by Claude Code, Cursor, and other tools)."*

2. **A separate registry format would duplicate a working native mechanism.** If the Orchestrator maintained its own `registry.json` mapping sub-agent names to invocation commands, every registry entry would need to (a) define the sub-agent's prompt (which Devin's profile body already does), (b) define its tool restrictions (which Devin's `allowed-tools` frontmatter already does), and (c) actually invoke the sub-agent — but the only way to invoke a sub-agent WITH those restrictions is to either pass them as CLI flags on each `devin` invocation (which Devin CLI does not support — see Section 2.7.3: there is no `--agent` flag) OR have Devin load them from a profile file. So a separate registry format would still need to write a profile file to disk for Devin to load. That's pointless indirection.

3. **The native profiles support tool restriction enforcement.** Verified in `subagents.md`: `allowed-tools` restricts the toolset; `subagent_explore` "cannot edit files or fetch arbitrary URLs (regardless of foreground or background)"; `ask_user_question` is always withheld from subagents. The enforcement is at Devin's runtime tool-injection layer, not advisory — which is what the brief requires.

4. **The native profiles support nesting control.** `max-nesting` frontmatter controls whether a sub-agent can spawn its own sub-agents (and to what depth). The brief asks whether the registry needs to support multiple concurrent instances of the same sub-agent role; `max-nesting` is the relevant mechanism (verified v2026.5.26-0, May 26, 2026).

5. **Cross-tool portability.** Because the format is shared by Claude Code, Cursor, and Devin, a sub-agent profile written for this harness can be reused in any of those tools without modification. This is a real benefit, not a theoretical one — the Serena project (`oraios/serena#1757`) and RTK (`rtk-ai/rtk#3143`) already treat the format as portable.

6. **The mapping to independent `devin` CLI session invocations is straightforward.** When the Orchestrator wants to run a sub-agent as a stage, it does NOT use Devin's native `run_subagent` tool (which runs the sub-agent IN the parent's session, sharing the parent's context window and compaction state — exactly what we're trying to avoid). Instead, the Orchestrator spawns an INDEPENDENT `devin -p "..." --prompt-file <task>` subprocess for the stage, with the sub-agent's profile loaded as the session's agent profile. (Section 3.6 details how.) This gives each stage its own context window, its own compaction, its own crash isolation — the core architectural requirement.

**Note on the `model` field:** Devin CLI's native subagent format supports a `model:` frontmatter field (verified in `subagents.md`), and the brief asks for "model preference" as a registry field. This spec intentionally does NOT use it — all sub-agents run on SWE-1.6 (Devin CLI's default subagent model), per the deployment decision recorded in Section 11.14. The field remains documented in Section 3.3.1 for completeness, but the Orchestrator does not read it, does not pass `--model` to the `devin` subprocess, and the `RegistryEntry` Pydantic model in Section 3.4.2 omits it. If model switching becomes a requirement later, adding it back is a one-line change to `RegistryEntry` and one flag to the subprocess invocation.

### 3.3 What a registry entry (sub-agent profile) contains

A registry entry is a markdown file at one of:
- `<project>/.devin/agents/<name>.md` (project-scoped, VCS-tracked)
- `~/.config/devin/agents/<name>.md` (user-scoped, global)
- `<project>/.devin/agents/<name>/AGENT.md` (directory layout; accepted filenames: `AGENT.md`, `AGENTS.md`, `agent.md`, `agents.md`, in that precedence order)

The file contains YAML frontmatter + a markdown body.

#### 3.3.1 Frontmatter fields (verified from `docs.devin.ai/cli/subagents.md`, accessed 2026-08-16)

| Field | Required | Default | Notes |
|---|---|---|---|
| `name` | No (defaults to filename) | filename without `.md` | Must not collide with built-ins (`subagent_explore`, `subagent_general`). Lowercase + hyphens. |
| `description` | Yes | — | Read by the parent agent to decide when to delegate. Also used by the Orchestrator as the human-readable label. |
| `model` | No | default subagent model (SWE-1.6) | **NOT USED by this harness** — all sub-agents run on SWE-1.6. Documented for completeness; the Orchestrator does not read this field. See Section 11.14. |
| `allowed-tools` | No | all tools | Restricts the toolset. Cannot grant `ask_user_question` (always withheld from subagents). |
| `max-nesting` | No | 0 (cannot spawn sub-agents) | Override max nesting depth so this sub-agent can spawn its own sub-agents. |

#### 3.3.2 Orchestrator-extension frontmatter fields (added by this harness)

The Orchestrator extends the frontmatter with its own fields (under an `orchestrator:` namespace, so they're ignored by Devin CLI's own subagent loader). These are read by the Orchestrator's registry loader but NOT by Devin's native mechanism.

```yaml
orchestrator:
  input_contract:
    type: object
    schema_ref: contracts/researcher-input.json   # path relative to project root
    required: true
  output_contract:
    type: object
    schema_ref: contracts/researcher-output.json
    required: true
    schema:                                       # inline alternative to schema_ref
      type: object
      required: [findings_md_path, sources_jsonl_path]
      properties:
        findings_md_path: {type: string}
        sources_jsonl_path: {type: string}
  timeout_seconds: 1800                           # hard wall-clock cap for this stage
  retry_policy:
    transient: {max_attempts: 3, backoff: exponential}
    logic_error: {max_attempts: 1, escalate: human}
    environment_error: {max_attempts: 5, backoff: linear}
  idempotency_key: "stage:${pipeline_run_id}:${stage_index}"  # see Section 6.7
  max_concurrent_instances: 2                     # for parallelizable stages
  human_approval_required: false                  # gates this stage behind PermissionRequest
```

**Why the `orchestrator:` namespace?** Devin CLI's subagent loader will ignore frontmatter fields it doesn't recognize (verified behavior — the docs only document `name`, `description`, `model`, `allowed-tools`, `max-nesting`). Putting Orchestrator-specific fields under a single namespace keeps the file valid as a Devin subagent profile while letting the Orchestrator's loader extract what it needs. (Note: the `model` field IS recognized by Devin CLI, but this harness does not set it — see Section 11.14.)

#### 3.3.3 The markdown body — the system prompt

The body of the `.md` file IS the sub-agent's system prompt. Devin CLI loads it verbatim. The Orchestrator does NOT modify it.

The brief states: *"the prompt content itself is out of scope — just the reference mechanism."* The reference mechanism is: the body of the `.md` file. No separate prompt file is needed; if one is desired (e.g., for very long prompts), the body can be a single line like `{{include: prompts/researcher.md}}` and the Orchestrator's loader can resolve the include before writing the resolved profile to a temp file for Devin to load. **This is an optional enhancement; Phase 1 of the build plan (Section 10) does NOT need it.**

### 3.4 How the Orchestrator discovers registered sub-agents at startup

**Three-step discovery process:**

#### 3.4.1 Scan the directories

At startup, the Orchestrator scans (in priority order, highest first):
1. `<project>/.devin/agents/` (project-scoped — checked into VCS, shared with team)
2. `~/.config/devin/agents/` (user-scoped — personal overrides)
3. (Optional, Phase 5) entry points under the `devin_orchestrator_agents` group — for pip-distributable sub-agent packs.

**Discovery mechanism:** directory glob. For each `*.md` file (or `<name>/AGENT.md`), parse the YAML frontmatter. The Orchestrator uses `python-frontmatter` (PyPI: `python-frontmatter`) or a 20-line hand-rolled YAML+markdown splitter (preferred for KISS — avoids the dependency).

**Why directory scan over a manifest file?** Two reasons:
1. **It matches the native mechanism.** Devin CLI's own loader scans `.devin/agents/`. If the Orchestrator also scans the same directory, the registry is consistent with what Devin sees — no risk of the Orchestrator knowing about a sub-agent that Devin doesn't, or vice versa.
2. **"Drop a file, restart, done" is the brief's explicit requirement.** A manifest file requires editing the manifest to add a sub-agent; a directory scan requires only dropping the file. The directory-scan pattern is validated by Airflow's DagBag (scans `DAGS_FOLDER` every 30s — `airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html`, accessed 2026-08-16), Dagster's `defs/` autoload (`docs.dagster.io/api/dagster/components`), and pytest's `conftest.py` + `test_*.py` discovery (`docs.pytest.org/en/stable/how-to/writing_plugins.html`).

#### 3.4.2 Parse the frontmatter

For each discovered profile, extract:
- `name` (or fall back to filename)
- `description`
- `allowed-tools` (or fall back to "all")
- `max-nesting` (or fall back to 0)
- `orchestrator.input_contract`, `orchestrator.output_contract`, `orchestrator.timeout_seconds`, `orchestrator.retry_policy`, `orchestrator.idempotency_key`, `orchestrator.max_concurrent_instances`, `orchestrator.human_approval_required`

**Note:** the `model` frontmatter field is intentionally NOT extracted — all sub-agents run on SWE-1.6. See Section 11.14.

Build an in-memory `RegistryEntry` (Pydantic v2 model):

```python
class RegistryEntry(BaseModel):
    name: str
    description: str
    profile_path: Path
    allowed_tools: list[str] | None = None       # None = all
    max_nesting: int = 0
    input_contract: ContractRef | None = None
    output_contract: ContractRef | None = None
    timeout_seconds: int = 3600
    retry_policy: RetryPolicy = RetryPolicy()
    idempotency_key_template: str | None = None
    max_concurrent_instances: int = 1
    human_approval_required: bool = False
    # NOTE: no `model` field — all sub-agents run on SWE-1.6 (Section 11.14).

class Registry(BaseModel):
    entries: dict[str, RegistryEntry] = {}       # keyed by name

    @classmethod
    def load(cls, project_agents_dir: Path, user_agents_dir: Path) -> "Registry":
        # Scan both dirs; user-scoped overrides project-scoped on name collision
        ...
```

#### 3.4.3 Validate against the pipeline

After loading the registry, the Orchestrator loads `pipeline.json` (Section 3.5) and validates that every stage in the pipeline references a registered sub-agent name. If any stage references an unknown name, the Orchestrator fails fast at startup with a clear error: `"Pipeline stage 3 references sub-agent 'reviewer' but no .devin/agents/reviewer.md was found. Scanned: <list of paths>."`

### 3.5 The pipeline is a separate `pipeline.json` — design and rationale

The brief asks: *"Whether the pipeline's sequence (or dependency graph, if it stops being a strict sequence) is itself part of the registry, so a new agent can be slotted in or branched off without touching Orchestrator logic."*

**Answer: yes, but as a separate file, not embedded in the registry.** The pipeline is `pipeline.json` (or `pipeline.yaml`), in `<project>/.devin/orchestrator/pipeline.json`. It references sub-agent profiles by name and declares their order and handoff conditions.

**Why separate from the registry?** The native subagent format has no concept of "pipeline position" — a sub-agent profile is just a profile; it doesn't know it's stage 3 of 5. Adding pipeline position to the subagent profile would couple the profile to a specific pipeline, breaking portability (the same `reviewer` profile might be stage 4 in one pipeline and not used at all in another). The pipeline is an Orchestrator concern, so it lives in an Orchestrator-owned file.

#### 3.5.1 `pipeline.json` schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "name": "default-pipeline",
  "version": "1.0.0",
  "stages": [
    {
      "id": "research",
      "subagent": "researcher",
      "input": {
        "task_prompt_file": "tasks/research-task.md"
      },
      "on_success": "plan",
      "on_failure": "fail"
    },
    {
      "id": "plan",
      "subagent": "planner",
      "input": {
        "task_prompt_file": "tasks/plan-task.md",
        "from_stage_outputs": ["research"]
      },
      "on_success": "implement",
      "on_failure": {"retry": 2, "then": "fail"}
    },
    {
      "id": "implement",
      "subagent": "implementor",
      "input": {
        "task_prompt_file": "tasks/implement-task.md",
        "from_stage_outputs": ["research", "plan"]
      },
      "on_success": "review",
      "on_failure": {"retry": 1, "then": "fail"}
    },
    {
      "id": "review",
      "subagent": "reviewer",
      "input": {
        "task_prompt_file": "tasks/review-task.md",
        "from_stage_outputs": ["implement"]
      },
      "on_success": "execute",
      "on_reject": {"bounce_to": "implement", "max_bounces": 2, "then": "escalate"}
    },
    {
      "id": "execute",
      "subagent": "executor",
      "input": {
        "task_prompt_file": "tasks/execute-task.md",
        "from_stage_outputs": ["review"]
      },
      "on_success": "complete",
      "on_failure": {"retry": 0, "then": "escalate"}
    }
  ],
  "terminal_states": {
    "complete": {"status": "succeeded"},
    "fail": {"status": "failed"},
    "escalate": {"status": "escalated", "notify": "human"}
  }
}
```

**Key fields:**
- `stages[].id`: a stable identifier for this stage INSTANCE in this pipeline (not the sub-agent name — the same sub-agent could appear twice in a pipeline). Used as the key in `workflow-state.json`'s `stage_states` map.
- `stages[].subagent`: the name of the registered sub-agent profile to invoke.
- `stages[].input.task_prompt_file`: path to the task-specific prompt (the initial user prompt passed to `devin -p` or `--prompt-file`). This is what makes a generic `researcher` profile reusable for different research tasks.
- `stages[].input.from_stage_outputs`: list of prior stage IDs whose output files should be referenced in this stage's task prompt. The Orchestrator resolves these to file paths and includes them in the prompt.
- `stages[].on_success`: the next stage ID to run on success.
- `stages[].on_failure`: either a stage ID (to bounce back), or `{"retry": N, "then": "fail"|"escalate"|"next_stage_id"}`, or `"fail"` / `"escalate"` directly.
- `stages[].on_reject`: optional — if the stage's output fails validation by the next stage's input contract, bounce back to a prior stage. `max_bounces` caps the loop; `then` is the terminal action.

#### 3.5.2 Why a strict sequence (not a DAG) for v1

The brief allows for a dependency graph ("if it stops being a strict sequence"). For v1, the spec uses a **strict sequence with conditional branches** (`on_success`, `on_failure`, `on_reject`). This covers:
- Linear pipelines (the 5-stage example).
- Retry-with-backoff (via `on_failure.retry`).
- Loopback / rejection (via `on_reject.bounce_to`).

It does NOT cover:
- Parallel stages (two sub-agents running at once whose outputs merge).
- Conditional fan-out (stage A's output determines which of stages B, C, D to run next).
- Cyclic pipelines with complex merge points.

**For v1 these are out of scope.** A future v2 could extend `stages` to `nodes` and `edges` (a DAG), but the state machine (Section 6) and the registry loader are designed so that this extension requires changes to the pipeline schema and the transition table, NOT to the Orchestrator's core loop. This is recorded as Section 11 risk (LOW).

#### 3.5.3 Adding a sixth sub-agent — the worked example

The brief's litmus test: *"adding a sixth agent... must be possible by changing configuration or data, not by editing the Orchestrator's code."*

**To add a "Tester" sub-agent between Implementor and Reviewer:**

1. Create `<project>/.devin/agents/tester.md`:
   ```markdown
   ---
   name: tester
   description: Writes and runs tests for the implementation. Use after implementation, before review.
   allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
   orchestrator:
     input_contract:
       schema_ref: contracts/tester-input.json
     output_contract:
       schema_ref: contracts/tester-output.json
     timeout_seconds: 2400
   ---
   You are a testing sub-agent. Read the implementation from the path given in the task prompt,
   write tests covering the public API, run them, and report results.
   ```
2. Edit `<project>/.devin/orchestrator/pipeline.json` to insert the `test` stage between `implement` and `review`:
   ```json
   {
     "id": "implement",
     "subagent": "implementor",
     "on_success": "test",          // was "review"
     ...
   },
   {
     "id": "test",                   // NEW
     "subagent": "tester",
     "input": {
       "task_prompt_file": "tasks/test-task.md",
       "from_stage_outputs": ["implement"]
     },
     "on_success": "review",
     "on_failure": {"retry": 2, "then": "fail"}
   },
   {
     "id": "review",
     ...
   }
   ```
3. Restart the Orchestrator. The state machine (Section 6) reads `pipeline.json` at startup and derives its states and transitions from it — no code change to the state machine.

**Zero code changes.** The Orchestrator's core loop, state machine, hook scripts, and memory system are unchanged.

### 3.6 What "spinning up a new sub-agent" concretely looks like

When the Orchestrator is ready to run stage `S` (per the state machine in Section 6), it:

1. **Looks up the registry entry** for `S.subagent` (e.g., `researcher`).
2. **Resolves the task prompt** by reading `S.input.task_prompt_file` and substituting any `from_stage_outputs` references with the actual file paths of prior stages' output files (read from `workflow-state.json`'s `stage_states[<prior_stage_id>].output_paths`).
3. **Writes the resolved task prompt to a temp file** (e.g., `/tmp/orchestrator-stage-<run_id>-<stage_id>-task.md`).
4. **Spawns the Devin CLI subprocess** via `asyncio.create_subprocess_exec`:
   ```python
   cmd = [
       "devin",
       "--config", str(project_config_path),          # points to .devin/config.json that loads our hooks
       # No --model flag: all sub-agents run on Devin CLI's default (SWE-1.6). See Section 11.14.
       "--permission-mode", "accept-edits",           # or per-stage config
       "--prompt-file", str(task_prompt_path),
       "--export", str(stage_export_path),             # ATIF export for post-stage parsing
       "--respect-workspace-trust", "false",           # CI-friendly
   ]
   if registry_entry.human_approval_required:
       cmd.append("--permission-mode"); cmd.append("normal")  # force interactive approval
   proc = await asyncio.create_subprocess_exec(
       *cmd,
       stdout=asyncio.subprocess.PIPE,
       stderr=asyncio.subprocess.PIPE,
       start_new_session=True,                         # so killpg reaches descendants
   )
   ```
5. **Waits for completion** with the liveness watchdog from Section 9 (heartbeat + inactivity timeout + hard wall-clock).
6. **Extracts the stage's output** by reading the file path declared in the registry entry's `output_contract` (the sub-agent writes its output to a contract-defined path; the Orchestrator reads that path on `Stop` — see Section 8).
7. **Validates the output** against the output contract's JSON schema (Section 8).
8. **Transitions the state machine** per `S.on_success` or `S.on_failure`.

**Why spawn an independent `devin` subprocess per stage (vs. use Devin's native `run_subagent` tool within one parent session)?**

The brief's core architectural requirement is: each stage gets its own context window, its own compaction, its own crash isolation. Devin's native `run_subagent` tool runs the sub-agent IN the parent's session — sharing the parent's context window and compaction state. That defeats the purpose. Spawning an independent `devin -p --prompt-file <task>` subprocess per stage gives each stage:
- Its own `session_id` (auditable in `action-log.jsonl`).
- Its own context window (no compaction bleed-over between stages).
- Its own crash isolation (if stage 3's `devin` process crashes, stages 1, 2, 4, 5 are unaffected).
- Its own `PostCompaction` events (compaction happens per-stage, between stages only — per the brief's compaction policy).

The trade-off: the Orchestrator cannot use Devin's native subagent delegation (the parent agent's `run_subagent` tool). Instead, the Orchestrator itself is the "parent" — it spawns `devin` subprocesses and manages handoffs. This is the correct architecture for the brief's requirements.

### 3.7 Concurrent instances of the same sub-agent role

The brief asks: *"Whether the registry needs to support multiple concurrent instances of the same sub-agent role (not just distinct named roles) — worth a brief look even if it's not the primary requirement."*

**Yes, the design supports it, but it's not the default.** The `orchestrator.max_concurrent_instances` frontmatter field (default 1) declares how many instances of this sub-agent may run in parallel. When the pipeline reaches a stage with `max_concurrent_instances > 1`, the Orchestrator spawns N independent `devin` subprocesses, each with a distinct `session_id`, each working on a different slice of the stage's input (e.g., the Implementor stage could parallelize across 3 source files, spawning 3 Implementor instances, each with a distinct `idempotency_key` derived from `stage_id + slice_index`).

**For v1, `max_concurrent_instances` defaults to 1 and the pipeline schema does not declare parallel slices.** The field exists to make the design forward-compatible without forcing parallelism on day one. Parallel execution requires a `parallel_slices` field in the pipeline schema (out of scope for v1 — see Section 11 risk LOW).

### 3.8 Hot-reload — optional, Phase 5

The brief doesn't require hot-reload (it says "restart or hot-reload"). For v1, the Orchestrator requires a restart to pick up new/changed sub-agent profiles. This matches Airflow's older behavior (pre-2020) and is acceptable for a local dev tool.

**Phase 5 enhancement:** Add `watchfiles.awatch(<project>/.devin/agents/)` to the Orchestrator's event loop. On any file change, re-scan the directory, rebuild the `Registry` model, atomically swap the in-memory registry, and log the change to `action-log.jsonl`. The pattern is validated by uvicorn's `--reload` (which uses `watchfiles` under the hood). Future sub-agent invocations use the new registry; in-flight invocations are unaffected (they already loaded their profile at spawn time).

**Why defer to Phase 5?** KISS. The registry changes rarely during a pipeline run; restart-on-change is fine for v1. Hot-reload adds complexity (atomic swap, in-flight isolation, schema-migration handling) that isn't justified until the harness is otherwise stable.

### 3.9 Proven patterns adapted — comparison table

| Pattern | Source | Adapted as |
|---|---|---|
| Markdown + YAML frontmatter, directory scan | Claude Code (`.claude/agents/`), Devin CLI (`.devin/agents/`) | The registry format itself — verbatim. |
| Strict sequence with conditional branches | Airflow DAGs (Python files in DAGS_FOLDER), Dagster `defs/` autoload | `pipeline.json` with `on_success`/`on_failure`/`on_reject`. |
| Optional entry-points for distributable plugins | pytest `pytest11` group, pluggy `load_setuptools_entrypoints` | Phase 5 only — `devin_orchestrator_agents` entry-point group. Not in v1. |
| Subprocess-as-plugin via JSON-over-stdio | Meltano/Singer (`meltano.yml` enumerates pip-installable executables speaking Singer JSON) | The `devin` CLI subprocess invocation pattern (Section 3.6). |
| Hot-reload via async FS watcher | uvicorn `--reload` via `watchfiles` | Phase 5 enhancement to the registry loader. |

---

## 4. Enforcement Model: Blocking vs. Non-Blocking

**Resolution to Must-Resolve Question 2.**

### 4.1 The recommendation, in one paragraph

**The Orchestrator uses hard-blocking (`exit 2` or `decision: block`) ONLY on `PreToolUse` hooks for unambiguously destructive commands that match a configurable denylist regex. Everything else — including `Stop`, `PostToolUse`, `PermissionRequest`, and all non-destructive `PreToolUse` matches — uses audit-log-plus-context-injection: log the event to `action-log.jsonl`, optionally inject a correction via `hookSpecificOutput.additionalContext` (or rewrite the call via `hookSpecificOutput.updatedInput` for `PreToolUse`), and let the agent continue.** The `Stop` hook NEVER blocks, period — the documented infinite-loop risk makes blocking `Stop` unacceptable.

### 4.2 Why this policy

Three constraints drive it:

1. **Devin CLI's `decision: block` cancels the WHOLE turn, not just the single tool call** (verified empirically by `oraios/serena#1757`, accessed 2026-08-16 — see Section 2.10). Using `decision: block` for soft corrections (e.g., "you used the wrong branch name, try again") would abort the entire sub-agent's turn, forcing the Orchestrator to either restart the stage (same impulse, same mistake) or fail it. That's worse than letting the agent self-correct.

2. **`Stop` hooks that always block cause infinite loops** (documented in Devin CLI's `lifecycle-hooks.md`: *"stop hooks that block can cause the agent to loop if the condition isn't eventually satisfied"*). If the Orchestrator's `Stop` hook blocks because, say, the output contract isn't satisfied, and the agent retries with the same approach, the hook blocks again, and the loop never terminates.

3. **KISS.** A single, consistent policy is easier to reason about, easier to audit, and easier to debug than a per-hook policy matrix. "Block only on destructive commands; audit + inject everywhere else" is one rule.

### 4.3 The policy, formalized

For each of the 8 hooks, the Orchestrator's hook script applies the following policy:

| Hook | Default action | Block (`exit 2` / `decision:block`)? | Inject `additionalContext`? | Rewrite via `updatedInput`? |
|---|---|---|---|---|
| `PreToolUse` | Audit to `action-log.jsonl`. If `tool_name` is `exec` and `tool_input.command` matches the destructive-command denylist → block. If it matches a "rewrite" rule (e.g., force `--no-destructive` flag) → rewrite via `updatedInput`. Otherwise → audit only, no block, no inject. | **YES, only for denylist matches.** | No (PreToolUse does not support additionalContext). | Yes, for "rewrite" rules (e.g., add `--dry-run` to a `git push`). |
| `PostToolUse` | Audit `tool_response` to `action-log.jsonl`. If `tool_response.success == false`, optionally inject a correction via `additionalContext` (e.g., "The previous command failed with: <error>. Consider <suggestion>."). | NO (PostToolUse does not support `decision` per docs). | Yes, on failure with a correction. | No (PostToolUse does not support updatedInput). |
| `PermissionRequest` | Audit the request. If `tool_name` is in the always-allow list → `decision: approve`. If `tool_name` is in the always-deny list → `decision: block`. If `human_approval_required` is set for the current stage → fall through (return no decision; Devin CLI falls back to its current permission mode, which the Orchestrator sets to `normal` to force interactive approval). | YES, for always-deny matches. | No (PermissionRequest does not support additionalContext). | No. |
| `UserPromptSubmit` | Audit the prompt. If the `workflow-state.json` flag `recovery_brief_needed` is set, build the brief from disk (Section 7) and inject via `additionalContext`. Clear the flag. | NO. | Yes, for recovery brief injection. | No. |
| `Stop` | Audit the stop event. Validate the stage's output contract (Section 8). If validation fails, set `workflow-state.json` flag `recovery_brief_needed` with a correction message; the next `UserPromptSubmit` (if the agent continues) or the next stage's `SessionStart` (if the agent stops) will inject the correction. **NEVER block.** | **NO — NEVER.** (Infinite-loop risk.) | No (Stop does not support additionalContext per docs). | No. |
| `PostCompaction` | Audit the compaction event to `action-log.jsonl`. Persist the compaction summary to `decisions.sqlite` for later retrieval. Set the `recovery_brief_needed` flag in `workflow-state.json`. **Do NOT attempt to inject `additionalContext`** (not supported per docs — see Section 2.6). | NO (PostCompaction does not support decision per docs). | NO (not supported per docs — use the next UserPromptSubmit instead). | No. |
| `SessionStart` | Audit the session start. If this is a resumed session (per `workflow-state.json`), inject the recovery brief via `additionalContext`. | NO. | Yes, for resumed sessions. | No. |
| `SessionEnd` | Audit the session end. If the session ended cleanly (reason = "completed"), mark the stage's `output_paths` in `workflow-state.json` from the contract-declared paths. If the session crashed (reason = "crash" or absent), mark the stage as `CRASHED_RECOVERABLE` (Section 6). | NO. | No. | No. |

### 4.4 The destructive-command denylist — default contents

The denylist is a regex list in `<project>/.devin/orchestrator/policy.json`:

```json
{
  "destructive_command_denylist": [
    {"pattern": "rm\\s+-rf\\s+/", "reason": "Recursive delete of root filesystem"},
    {"pattern": "rm\\s+-rf\\s+~", "reason": "Recursive delete of home directory"},
    {"pattern": "rm\\s+-rf\\s+\\$HOME", "reason": "Recursive delete of home directory"},
    {"pattern": "git\\s+push\\s+.*--force\\s+.*main", "reason": "Force-push to main branch"},
    {"pattern": "git\\s+push\\s+.*--force\\s+.*master", "reason": "Force-push to master branch"},
    {"pattern": "DROP\\s+(TABLE|DATABASE)", "reason": "Dropping database tables"},
    {"pattern": "sudo\\s+rm", "reason": "Recursive delete with elevated privileges"},
    {"pattern": ":\\(\\)\\s*\\{\\s*:|:&\\s*\\};:", "reason": "Fork bomb"},
    {"pattern": "dd\\s+if=.*/dev/.*of=/dev/sd", "reason": "Direct write to block device"},
    {"pattern": "mkfs\\.", "reason": "Filesystem format"}
  ],
  "rewrite_rules": [
    {
      "pattern": "git\\s+push\\s+(?!.*--dry-run)",
      "rewrite_to": {"command": "git push --dry-run $1"},
      "reason": "Force --dry-run on all git push commands in CI/orchestration context"
    }
  ],
  "always_allow_tools": ["Read", "Grep", "Glob", "TodoWrite"],
  "always_deny_tools": []
}
```

**Why a denylist and not an allowlist?** An allowlist ("only these specific commands may run") is safer in principle but unworkable in practice for a coding agent — the agent needs broad tool access to do its job, and predicting every safe command is impossible. A denylist of unambiguously destructive commands (rm -rf /, force-push to main, DROP TABLE, fork bombs, mkfs) catches the catastrophic cases without paralyzing the agent. This matches the convention in production coding-agent harnesses (Claude Code's default permission prompts, Cursor's command gating).

### 4.5 Why `Stop` never blocks — the loop-prevention pattern

The documented warning (Section 2.1): *"stop hooks that block can cause the agent to loop if the condition isn't eventually satisfied."*

The Orchestrator's `Stop` hook validates the stage's output contract (Section 8). If validation fails, the hook:

1. **Audits the failure** to `action-log.jsonl` with the validation error.
2. **Sets `workflow-state.json.stage_states[<stage_id>].recovery_brief_needed = true`** with a `recovery_message` field explaining what's wrong ("Output file `/tmp/research-findings.md` does not exist; the Researcher's output contract requires it.").
3. **Returns `exit 0`** (does NOT block).

If the agent stops again without satisfying the contract, the state machine's retry policy (per `pipeline.json`'s `on_failure`) governs whether to retry the stage or escalate. The `Stop` hook itself never blocks — the loop is bounded by the retry policy, not by the hook.

### 4.6 The recovery-brief injection pattern

The `recovery_brief_needed` flag is the Orchestrator's mechanism for injecting corrections without blocking. It's set by `Stop` (output contract failure), `PostCompaction` (state lost), or `PostToolUse` (tool failure with a known correction). It's consumed by the next `UserPromptSubmit` or `SessionStart` hook, which:

1. Reads the flag and the `recovery_message` from `workflow-state.json`.
2. Builds a recovery brief by combining:
   - The `recovery_message`.
   - The current stage's id, subagent name, and task prompt path.
   - A summary of prior stages' outputs (from `workflow-state.json.stage_states[<prior_stage_id>].output_paths`).
   - A retrieval from `decisions.sqlite` (FTS5 query: `stage_id + subagent_name + "decision"`) for any past decisions relevant to this stage.
3. Returns the brief as `hookSpecificOutput.additionalContext`.
4. Clears the flag.

**This is the only sanctioned re-injection channel.** Per Section 2.6, `PostCompaction` cannot inject; `UserPromptSubmit` and `SessionStart` are the documented channels.

### 4.7 Human-approval gates — when and how

The brief asks: *"Should there be a human-approval gate anywhere — before a destructive stage runs, for instance — and if so, how does that map onto the hook system (`PermissionRequest`)?"*

**Yes, for stages with `human_approval_required: true` in the registry entry's `orchestrator:` block.** The mechanism:

1. The Orchestrator spawns the stage's `devin` subprocess with `--permission-mode normal` (forcing interactive approval for every permission-gated action).
2. When the sub-agent attempts a permission-gated action, Devin CLI fires `PermissionRequest`.
3. The Orchestrator's `PermissionRequest` hook audits the request and **returns no decision** (exit 0, empty stdout). Devin CLI then falls back to its current permission mode (`normal`), which prompts the human operator interactively.
4. The human approves or denies. The result is captured in the next `PostToolUse` event's `tool_response.success` field (audited to `action-log.jsonl`).

**For stages WITHOUT `human_approval_required`**, the Orchestrator spawns with `--permission-mode accept-edits` (or `auto` for fully autonomous stages), and the `PermissionRequest` hook auto-approves from the always-allow list and auto-denies from the always-deny list, falling through otherwise.

**Where to set `human_approval_required: true`:** stages that perform destructive real-world actions — e.g., an Executor that runs `terraform apply`, a Deployer that pushes to production, a Migrator that runs `DROP COLUMN` on a production DB. The 5-stage example pipeline does NOT need this (Executor runs tests, not deployments). It's a per-stage decision in the registry entry.

---

## 5. Memory Stack Specification

### 5.1 Headline — the KISS stack is validated

The brief's planned storage stack (`workflow-state.json` + `action-log.jsonl` + `decisions.sqlite` with FTS5) is **validated by multiple 2026 production systems**. None of the named memory systems (Letta, Mem0, Zep, LangGraph, AutoGen) is a drop-in fit for this harness — each either requires infrastructure the harness rejects (Postgres, Neo4j, an embedding model, a separate server) or couples the memory store to its own agent loop. But the *patterns* those systems use, and several other production systems that use the same KISS stack, validate every layer of the planned design.

### 5.2 The memory stack table

| Memory type | Proven reference implementation (with source) | Storage backend chosen for this harness | Hooks that READ it | Hooks that WRITE it | Retention / pruning policy |
|---|---|---|---|---|---|
| **Working** (live state of current stage) | **DeerFlow** (`github.com/bytedance/deer-flow`) — `memory.json` with journaled writes + optimistic revisions. **Hermes Agent** — `MEMORY.md`/`USER.md` frozen-snapshot pattern. Both verified 2026-08-16. | `workflow-state.json` — single file, atomic write via temp + fsync + `os.replace` + fsync dir (Section 6.5). Pydantic v2 model serialized via `model_dump_json(indent=2)`. | `SessionStart`, `UserPromptSubmit`, `PostCompaction`, `Stop`, `SessionEnd` | `SessionStart`, `PostToolUse` (heartbeat), `Stop`, `PostCompaction`, `SessionEnd` | Pruned at pipeline completion (file archived to `archive/<run_id>/workflow-state.json`). No mid-run pruning — working memory must be complete. |
| **Episodic** (ordered run history) | **WorkOS audit harness** (ships plugins for 6 coding agents — verified 2026-08-16). **Hermes Agent #487** — proposes `~/.hermes/audit/trail.jsonl` with SHA-256 hash chaining. **AWS CloudTrail** — hourly digest files with linear hash chain + RSA signatures. | `action-log.jsonl` — append-only, `O_APPEND` + single `write()` + `fsync` per record, SHA-256 hash chain for tamper-evidence (Section 5.4). | `SessionStart` (recovery), `UserPromptSubmit` (recovery brief), `PostCompaction` (recovery brief), `Stop` (validation context) | Every hook (each event appends one record) | Append-only forever; rotated by run_id into `archive/<run_id>/action-log.jsonl` at pipeline completion. Hash chain head anchored to `decisions.sqlite` periodically for tamper-detection. |
| **Semantic / long-term** (retrievable facts and past decisions) | **OpenClaw Memory** — pure stdlib + SQLite FTS5, **zero-dep by deliberate design**, 26ms queries. **Hermes Agent** — `state.db` with FTS5, ~20ms. **DeerFlow** — "scope-aware SQLite FTS5/BM25 adapter by default." **memweave** — Markdown + FTS5 + sqlite-vec hybrid (weights 0.7×vector + 0.3×BM25). All verified 2026-08-16. | `decisions.sqlite` — single file, WAL mode, `synchronous=FULL`, FTS5 external-content table + triggers (Section 5.5). BM25 ranking. | `UserPromptSubmit` (recovery brief retrieval), `SessionStart` (recovery brief), `Stop` (decision context) | `PostToolUse` (decision extraction), `Stop` (decision finalization), `PostCompaction` (summary persistence) | Decisions never deleted. FTS5 index auto-maintained by triggers. Vacuum monthly. Optionally prune decisions older than `retention_days` (default: never). |
| **Shared / blackboard** (state visible to all sub-agents) | **LangGraph** shared store namespace (`InMemoryStore`/`PostgresStore` with namespace-scoped key-value). **Letta** shared memory blocks (prefix-injected into multiple agents' context). **DeerFlow** per-user `memory.json` shared across agents. All verified 2026-08-16. | `workflow-state.json`'s `shared_context` field (live shared state, written by `PostToolUse`) + `shared_facts` table in `decisions.sqlite` (queryable shared facts, written by `Stop`). **No separate blackboard system.** | `SessionStart` (injects `shared_context` into recovery brief), `UserPromptSubmit` (injects `shared_context`), `Stop` (reads `shared_facts` for validation context) | `PostToolUse` (writes to `shared_context`), `Stop` (writes to `shared_facts`) | `shared_context` is per-run; cleared at pipeline completion. `shared_facts` is per-project; pruned manually or by FTS5 relevance score. |
| **Procedural** (rules and conventions sub-agents should follow) | **Claude Code** `CLAUDE.md` + `.claude/rules/`. **Hermes** `MEMORY.md`. **LangGraph** example loads `default_triage_instructions` into the store on first run. **Cursor** `.cursor/rules/`. All verified 2026-08-16. | **NOT in the memory store.** Procedural rules live in: (a) each sub-agent profile's markdown body (the system prompt — Section 3.3.3), and (b) a project-level `AGENTS.md` at the project root (the cross-tool convention, read by Devin CLI, Claude Code, Cursor, and others). | Not applicable — procedural memory is injected by Devin CLI itself at session start, not by an Orchestrator hook. | Not applicable — written by humans, version-controlled. | Version-controlled with the project. No runtime pruning. |

### 5.3 Why each layer's storage choice is correct, with evidence

#### 5.3.1 Working memory — `workflow-state.json`

**The brief's plan is sufficient.** A single JSON file with atomic-replace writes is the canonical pattern for live state in local-first systems. Evidence:

- **DeerFlow (ByteDance)** uses `memory.json` with journaled writes and optimistic revisions — same pattern, validated in production. (Source: `github.com/bytedance/deer-flow`, accessed 2026-08-16.)
- **Hermes Agent** uses a frozen-snapshot `MEMORY.md`/`USER.md` pattern — same atomic-write semantics. (Source: `github.com/NousResearch/hermes-agent`, accessed 2026-08-16.)
- **LangGraph's `SqliteSaver` checkpointer** persists graph state to SQLite per-thread — a more complex version of the same idea (per-thread state). The harness doesn't need per-thread state (it has per-stage state, which is finer-grained), so the simpler single-file approach is preferred.

**What's missing from a bare JSON file?** Three things, all addressed in Section 6:
1. **Atomic write semantics** — temp + fsync + `os.replace` + fsync dir (Section 6.5).
2. **Schema validation** — Pydantic v2 model with `model_validator` for state-machine invariants (Section 6.4).
3. **Concurrency safety** — single-writer (the Orchestrator) + advisory file lock (`fcntl.flock`) to detect accidental concurrent Orchestrator instances (Section 6.8).

#### 5.3.2 Episodic memory — `action-log.jsonl`

**JSONL is the right choice.** Evidence:

- **WorkOS audit harness** ships JSONL audit plugins for 6 coding agents (Claude, Codex, OpenClaw, OpenCode, Hermes, pi). The format is append-only JSONL with per-event structured fields. (Source: WorkOS docs, accessed 2026-08-16.)
- **Hermes Agent #487** proposes `~/.hermes/audit/trail.jsonl` with SHA-256 hash chaining for tamper-evidence — exactly the pattern this spec adopts. (Source: `github.com/NousResearch/hermes-agent/issues/487`, accessed 2026-08-16.)
- **AWS CloudTrail** uses hourly digest files with a linear hash chain + RSA signatures for tamper-evidence — the production-grade version of the same pattern. (Source: `docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html`, accessed 2026-08-16.)

**Alternatives considered:**

| Alternative | Why rejected |
|---|---|
| SQLite table | Adds a transaction per event; harder to tail with `tail -f`; harder to grep; harder to recover from corruption. JSONL is human-readable and toolable. |
| NDJSON (newline-delimited JSON, same as JSONL) | Same thing — JSONL is NDJSON. No real difference. |
| MessagePack | Binary, not human-readable, harder to debug. The size savings (~30% smaller than JSON) are irrelevant at the volumes this harness produces (hundreds to low thousands of events per run). |
| Structured logging (structlog, loguru) to a file | These are frameworks, not formats. They can write JSONL, but they add a dependency and a layer of indirection for no benefit. Use `json.dumps` + `open(path, "a")` directly. |

**Hash chaining** is added (Section 5.4) for tamper-evidence. Per NIST SP 800-92 (accessed 2026-08-16), the threat model for a local audit log is: a same-user process (a malicious or buggy sub-agent) attempting to cover its tracks by editing the log. Append-only + `chmod 600` does not stop this; hash-chaining makes any in-place edit detectable on read. For full tamper-evidence against a same-user adversary who can rewrite the entire file, an external anchor is needed (Section 9.3).

#### 5.3.3 Semantic memory — `decisions.sqlite` with FTS5 + BM25

**FTS5 keyword search with BM25 ranking is sufficient.** Evidence:

- **OpenClaw Memory** uses pure stdlib + SQLite FTS5 by deliberate design — zero dependencies, 26ms queries on a moderate decision corpus. (Source: OpenClaw repo, accessed 2026-08-16.)
- **Hermes Agent** uses `state.db` with FTS5, ~20ms per query. (Source: `github.com/NousResearch/hermes-agent`, accessed 2026-08-16.)
- **DeerFlow** uses a "scope-aware SQLite FTS5/BM25 adapter by default" — explicitly choosing FTS5 over vector search. (Source: `github.com/bytedance/deer-flow`, accessed 2026-08-16.)

**Why FTS5 over embeddings?**

| Criterion | FTS5 + BM25 | Embeddings + vector DB |
|---|---|---|
| Dependencies | Zero (Python stdlib `sqlite3` ships FTS5 — verified Section 5.5.2) | Embedding model (sentence-transformers, OpenAI, etc.) + vector DB (Qdrant, Chroma, sqlite-vec) |
| Query latency | ~20-30ms (verified OpenClaw, Hermes) | ~50-200ms (embedding query + vector search) |
| Index build cost | None (FTS5 index built incrementally by triggers) | Must embed every decision at write time (1 LLM call per decision) |
| Retrieval quality for natural-language decisions | Sufficient — decisions are short, keyword-rich, and self-describing | Marginally better for paraphrased queries, but decisions rarely need paraphrase matching |
| Local-first / offline | Yes (no API calls) | Only if using a local embedding model (sentence-transformers); OpenAI embeddings require network |
| KISS fit | High | Low |

**The KISS constraint decides it.** FTS5 is zero-dependency, runs in <30ms per query in production, and is sufficient for natural-language decision retrieval because decisions are short, keyword-rich, and self-describing. Embeddings would marginally improve retrieval for paraphrased queries (e.g., "how did we handle the auth bug" matching a decision titled "OAuth token refresh logic"), but the marginal benefit does not justify the added complexity (embedding model, vector index, index rebuild on schema change).

**The upgrade path (if FTS5 proves insufficient):** Adopt **memweave's hybrid pattern** — FTS5 + `sqlite-vec` (a SQLite extension for vector search), with weighted scores (e.g., `0.7×vector + 0.3×BM25`). This stays single-file (no Qdrant/Postgres) and is the documented escape hatch. Section 11 records this as a MEDIUM risk: "FTS5 may prove insufficient for paraphrased queries; the upgrade path is `sqlite-vec` hybrid, which stays KISS."

#### 5.3.4 Shared / blackboard memory — `workflow-state.json` + `decisions.sqlite`

**The harness does NOT need a separate blackboard system.** The brief asks: *"Determine whether this harness needs one."*

**Answer: no, by design.** The harness's architecture is strict handoff (each stage's output is written to disk, the next stage reads it). There is no moment when two sub-agents are simultaneously working on the same problem and need to see each other's intermediate state. (If parallel stages are added in v2 — Section 3.7 — a blackboard would become necessary; for v1, it's not.)

However, two forms of "shared state" ARE useful:

1. **Live shared context** — small pieces of state every sub-agent should see (e.g., "the project uses ESM imports only", "the auth library is library X not Y"). This lives in `workflow-state.json.shared_context` (a small dict of key-value pairs). It's injected into every sub-agent's recovery brief by `SessionStart` and `UserPromptSubmit`. Written by `PostToolUse` when a sub-agent discovers a project-level fact worth sharing.

2. **Queryable shared facts** — durable facts that any future sub-agent can retrieve by keyword (e.g., "all past decisions about the auth module"). This lives in the `shared_facts` table in `decisions.sqlite` (with its own FTS5 index). Written by `Stop` when a stage completes and has extracted durable facts from its run. Read by `Stop` of future stages for validation context.

This covers both use cases without introducing a new storage layer or a new concept.

#### 5.3.5 Procedural memory — sub-agent profiles + AGENTS.md

**Procedural rules belong in prompts, not in the memory store.** This is the cross-tool convention, validated by:

- **Claude Code** `CLAUDE.md` (project-level rules, always loaded).
- **Hermes Agent** `MEMORY.md` (same pattern).
- **Cursor** `.cursor/rules/` (same pattern, different path).
- **Devin CLI** `AGENTS.md` / `AGENT.md` / `CLAUDE.md` (the cross-tool standard — Devin's docs explicitly state it reads all three filenames at the project root).
- **LangGraph** example loads `default_triage_instructions` into the store on first run — a pattern that puts procedural rules IN the memory store, but only as a one-time bootstrap, not as a runtime-updatable layer.

**Why not in the memory store?** Procedural rules are:
- Written by humans, not by agents.
- Version-controlled with the project.
- Loaded once at session start, not retrieved mid-session.
- Static across a pipeline run.

Putting them in `decisions.sqlite` would conflate human-authored rules with agent-produced decisions, making both harder to reason about. The brief explicitly states procedural memory is *"entirely a matter for each sub-agent's own prompt content (out of scope here)"* — this spec agrees and excludes it from the memory store.

### 5.4 The `action-log.jsonl` hash-chain schema

Every record in `action-log.jsonl` is a single JSON object on one line, with a SHA-256 hash chain for tamper-evidence:

```jsonl
{"seq": 1, "ts": "2026-08-16T12:00:00.123Z", "session_id": "abc-123", "prompt_id": "def-456", "hook_event": "SessionStart", "stage_id": "research", "payload": {"source": "cli"}, "prev_hash": "genesis", "hash": "9f2c..."}
{"seq": 2, "ts": "2026-08-16T12:00:01.456Z", "session_id": "abc-123", "prompt_id": "def-456", "hook_event": "UserPromptSubmit", "stage_id": "research", "payload": {"prompt": "Research the auth module..."}, "prev_hash": "9f2c...", "hash": "a1b2..."}
{"seq": 3, "ts": "2026-08-16T12:00:05.789Z", "session_id": "abc-123", "prompt_id": "def-456", "hook_event": "PreToolUse", "stage_id": "research", "payload": {"tool_name": "exec", "tool_input": {"command": "grep -r auth src/"}}, "prev_hash": "a1b2...", "hash": "c3d4..."}
```

**Fields:**
- `seq`: monotonic integer (1-based). Reset per run.
- `ts`: ISO-8601 UTC timestamp with milliseconds.
- `session_id`: from the hook payload (stable per session).
- `prompt_id`: from the hook payload (rotates per turn; absent for `SessionStart`).
- `hook_event`: the event name (e.g., `PreToolUse`).
- `stage_id`: the current stage's ID from `pipeline.json` (looked up by `session_id` → stage mapping in `workflow-state.json`).
- `payload`: the event-specific payload (verbatim from the hook's stdin, minus the common fields already extracted).
- `prev_hash`: SHA-256 hex of the previous entry's canonical serialization (excluding its own `hash` field). The first entry has `prev_hash = SHA256("genesis")`.
- `hash`: SHA-256 hex of THIS entry's canonical serialization (including `prev_hash`, excluding `hash` itself).

**Canonical serialization for hashing:** `json.dumps(entry_without_hash, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` — deterministic, no whitespace.

**Verification (read-side):** walk the log, recompute each `prev_hash` and `hash`, and check they match. Any mismatch indicates tampering or corruption. See Section 9.3 for the verification procedure and the external-anchor pattern.

### 5.5 The `decisions.sqlite` schema

#### 5.5.1 Schema

```sql
-- Regular table: structured decision fields
CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,                  -- ISO-8601 UTC
    pipeline_run_id TEXT NOT NULL,
    stage_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    subagent    TEXT NOT NULL,
    decision_type TEXT NOT NULL,                 -- 'stage_output' | 'tool_choice' | 'rejection' | 'recovery' | 'compaction_summary'
    rationale   TEXT NOT NULL,                   -- short summary
    body        TEXT NOT NULL,                  -- full searchable text
    metadata    TEXT                             -- JSON blob for stage-specific fields
);

-- FTS5 external-content virtual table indexing 'body'
CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts
    USING fts5(body, content='decisions', content_rowid='id');

-- Triggers to keep FTS in sync (per sqlite.org/fts5.html canonical example)
CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
    INSERT INTO decisions_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON decisions BEGIN
    INSERT INTO decisions_fts(decisions_fts, rowid, body)
        VALUES ('delete', old.id, old.body);
END;
CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON decisions BEGIN
    INSERT INTO decisions_fts(decisions_fts, rowid, body)
        VALUES ('delete', old.id, old.body);
    INSERT INTO decisions_fts(rowid, body) VALUES (new.id, new.body);
END;

-- Shared facts (separate from decisions; written by Stop on stage completion)
CREATE TABLE IF NOT EXISTS shared_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    stage_id    TEXT NOT NULL,
    fact_key    TEXT NOT NULL,
    fact_value  TEXT NOT NULL,
    rationale   TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS shared_facts_fts
    USING fts5(fact_key, fact_value, content='shared_facts', content_rowid='id');

-- Triggers for shared_facts (same pattern as decisions)

-- Connection pragmas (run once per connection)
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

**Search query:**
```sql
SELECT id, body, bm25(decisions_fts) AS score
FROM decisions_fts
WHERE decisions_fts MATCH ?
ORDER BY score  -- bm25 returns negative scores; lower = more relevant
LIMIT 20;
```

**Pitfall (from FTS5 docs):** creating the triggers does not copy existing rows. If the table is created after data exists, run `INSERT INTO decisions_fts(decisions_fts) VALUES('rebuild');` once.

#### 5.5.2 FTS5 availability in Python stdlib — verification

**Verified empirically on Python 3.12.13 + SQLite 3.53.1:** `CREATE VIRTUAL TABLE t USING fts5(content)` works out of the box.

**Verified in CPython source:** For official Python builds on Windows, `PCbuild/sqlite3.vcxproj` explicitly defines `SQLITE_ENABLE_FTS5` (along with `SQLITE_ENABLE_FTS4`, `SQLITE_ENABLE_RTREE`, `SQLITE_ENABLE_MATH_FUNCTIONS`). Confirmed identical for Python 3.11, 3.12, and 3.13 tags. (Sources: `github.com/python/cpython/blob/v3.11.0/PCbuild/sqlite3.vcxproj`, `github.com/python/cpython/blob/v3.12.0/PCbuild/sqlite3.vcxproj`, `github.com/python/cpython/blob/v3.13.0/PCbuild/sqlite3.vcxproj`, all accessed 2026-08-16.)

**The SQLite amalgamation** (the bundled `sqlite3.c` used by CPython on Windows and many Linux distros) **has FTS5 enabled by default since SQLite 3.9.0 (2015-10-14).** (Source: `sqlite.org/fts5.html`, accessed 2026-08-16.)

**EXPLICIT FLAG — could not verify:** The Python `sqlite3` docs at `docs.python.org/3/library/sqlite3.html` do NOT explicitly document FTS5 availability. On Linux/macOS, Python's `sqlite3` module links to the system libsqlite3, and FTS5 availability depends on the distro. Most modern distros (Ubuntu 20.04+, Debian 11+, Fedora 32+, macOS 11+) enable it. Older or minimal distros may not.

**Mitigation:** The Orchestrator MUST probe at startup:
```python
def verify_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
    except sqlite3.OperationalError as e:
        if "no such module: fts5" in str(e):
            raise RuntimeError(
                "FTS5 is not available in your SQLite build. "
                "Install pysqlite3-binary (pip install pysqlite3-binary) "
                "or rebuild Python with SQLITE_ENABLE_FTS5."
            ) from e
        raise
```

If FTS5 is unavailable, the Orchestrator fails fast at startup with a clear error message. The user can install `pysqlite3-binary` (PyPI) which is statically linked with FTS5. (Source: `pypi.org/project/pysqlite3-binary`, accessed 2026-08-16.)

### 5.6 How every sub-agent — including ones that don't exist yet — gets access to memory without further memory-system changes

**This is the brief's hard constraint:** *"A memory pattern that can't be pinned to a specific hook, or that needs code changes for every new sub-agent, isn't usable here."*

**The design satisfies it because memory access is mediated entirely by hooks, and hooks are registered globally (in `.devin/hooks.v1.json`), not per-sub-agent.** Every sub-agent the registry spins up — including ones that don't exist yet — runs under the same Devin CLI config, which loads the same `.devin/hooks.v1.json`, which fires the same 8 Orchestrator hook scripts. The hook scripts read/write the memory layers based on the current stage's ID (looked up from `session_id` in `workflow-state.json`), not based on the sub-agent's name.

**Concretely:** when a future sub-agent `archivist` (not in the original 5) is registered by dropping `archivist.md` into `.devin/agents/`, the Orchestrator:

1. Spawns `devin -p --prompt-file <task>` for the `archivist` stage.
2. Devin CLI loads `.devin/hooks.v1.json` (unchanged).
3. Every hook fires for the `archivist` session exactly as it does for `researcher` or `planner`.
4. The hook scripts look up the current stage by `session_id` in `workflow-state.json`, find `stage_id = "archive"`, and apply the same memory-layer reads/writes as for any other stage.
5. The `archivist` sub-agent's output is written to its contract-declared path, validated by the `Stop` hook, and its decisions are extracted by `PostToolUse` and written to `decisions.sqlite`.

**Zero memory-system code changes.** The only thing that changed was: a new `.md` file in `.devin/agents/` and a new stage entry in `pipeline.json`. The hook scripts, the memory schemas, the state machine — all unchanged.

### 5.7 Why the named memory systems are NOT used as runtime dependencies

| System | Why it's a reference, not a dependency |
|---|---|
| **Letta (formerly MemGPT)** | The legacy server requires Postgres + pgvector. The new Agent SDK is TypeScript + an in-memory filesystem (MemFS) — not Python, not persistent to disk in a way the harness can introspect. The Python `letta-client` (v1.12.1, July 2026) is explicitly "previous-generation." **Verdict: borrow the memory-blocks-as-XML-prefix pattern; do not depend on the runtime.** (Source: `github.com/letta-ai/letta`, accessed 2026-08-16.) |
| **Mem0** | Requires an LLM + embedding model + Qdrant even in library mode. Every `add()` call makes an LLM call to extract facts — adding latency and cost to every decision write. **Verdict: borrow the single-pass ADD-only fact-extraction prompt design; do not depend on the runtime.** (Source: `github.com/mem0ai/mem0`, accessed 2026-08-16.) |
| **Zep / Graphiti** | Zep Community Edition is **deprecated** (April 2025 strategy blog). The OSS graph engine lives in `getzep/graphiti` and requires Neo4j + an LLM + embeddings. **Verdict: borrow the bi-temporal model (event time vs. ingestion time) for the `decisions` table schema; do not depend on the runtime.** (Sources: `getzep.com`, `github.com/getzep/graphiti`, accessed 2026-08-16.) |
| **LangGraph** | The checkpointer (per-thread state) + store (cross-thread long-term) split is exactly the right pattern. But `SqliteStore` had a SQL-injection CVE (GHSA-7p73-8jqx-23r8, Oct 2025) and `AsyncSqliteStore` is "not recommended for production." `InMemoryStore` doesn't persist. `PostgresStore` requires Postgres. **Verdict: borrow the checkpointer/store split (working memory = checkpointer, semantic memory = store); implement with our own SQLite + FTS5, not LangGraph's store.** (Source: `github.com/langchain-ai/langgraph`, accessed 2026-08-16.) |
| **AutoGen** | The `Memory` ABC (`add`/`query`/`update_context`/`clear`/`close`) is clean and worth borrowing as an interface. But AutoGen is **in maintenance mode** as of 2026 — Microsoft Agent Framework (MAF) 1.0 is the production successor. Could not verify whether MAF preserves the `Memory` protocol. **Verdict: borrow the ABC shape for our own `Memory` base class; do not depend on AutoGen.** (Source: `github.com/microsoft/autogen`, accessed 2026-08-16.) |

---

## 6. State Machine Specification

### 6.1 The design principle — config-driven, not hardcoded

The state machine is **derived from `pipeline.json`**, not hardcoded. The Orchestrator's state machine code is generic: it reads `pipeline.json` at startup, builds an in-memory transition table, and applies transitions based on the current state and the fired event. Adding a sixth stage to `pipeline.json` requires ZERO changes to the state machine's code.

The five example stages (Researcher → Planner → Implementor → Reviewer → Executor) appear ONLY as illustrative `pipeline.json` entries. The state machine's code never references them by name.

### 6.2 The per-stage state cycle — generic

Every stage in the pipeline progresses through the following per-stage states:

```
PENDING → RUNNING → COMPLETE
              ↓         ↓
            FAILED    REJECTED (→ bounce_to stage per pipeline.json)
              ↓
        CRASHED_RECOVERABLE
              ↓
        CRASHED_UNRECOVERABLE (after max retries)
```

**State definitions:**

| State | Meaning | Entered when | Exited when |
|---|---|---|---|
| `PENDING` | Stage is queued, not yet started. | Pipeline initialization, or prior stage's `on_success` points here. | Orchestrator spawns the `devin` subprocess. |
| `RUNNING` | The `devin` subprocess for this stage is alive. | Orchestrator spawns the subprocess. | Subprocess exits, OR `Stop` hook fires and output contract is validated. |
| `COMPLETE` | Stage finished, output contract satisfied, output written to disk. | `Stop` hook validates output contract successfully AND subprocess exits cleanly. | Next stage's `PENDING` → `RUNNING` transition (per `on_success`). |
| `FAILED` | Stage finished but output contract NOT satisfied, OR subprocess exited non-zero. | `Stop` hook validates output contract and fails, OR subprocess exits non-zero. | Retry policy kicks in (per `on_failure`). |
| `REJECTED` | A downstream stage's input contract validation rejected this stage's output. | Downstream stage's `SessionStart` or `Stop` hook detects invalid input. | Bounce-to stage's `PENDING` → `RUNNING` (per `on_reject.bounce_to`). |
| `CRASHED_RECOVERABLE` | The Orchestrator process crashed mid-stage; on restart, the stage's output was incomplete. | Orchestrator restart detects incomplete output for a `RUNNING` stage. | Stage restarts (resumes from `PENDING` with the same `idempotency_key`). |
| `CRASHED_UNRECOVERABLE` | Stage has been retried `max_attempts` times (per retry policy) and still fails. | Retry policy exhausted. | Never (terminal state). Triggers escalation. |
| `ESCALATED` | Stage failed and retry policy says `then: escalate`. | Retry policy exhausted OR `on_failure: escalate`. | Never (terminal state). Notifies human. |

### 6.3 The transition table — generic, expressed in terms of "current stage" and "next stage per the registry"

| From state | Event | Guard condition | To state | Side effect |
|---|---|---|---|---|
| `PENDING` | Orchestrator ready to run stage | Subprocess spawn succeeds | `RUNNING` | Write `stage_states[<stage_id>].started_at` to `workflow-state.json`. Audit `stage.start` to `action-log.jsonl`. |
| `PENDING` | Orchestrator ready to run stage | Subprocess spawn fails | `FAILED` (transient) | Audit `stage.spawn_failed` to `action-log.jsonl`. Apply transient retry policy. |
| `RUNNING` | `Stop` hook fires | Output contract validates successfully AND subprocess exit code == 0 | `COMPLETE` | Write `stage_states[<stage_id>].completed_at` and `output_paths` to `workflow-state.json`. Audit `stage.complete` to `action-log.jsonl`. Extract decisions to `decisions.sqlite` (via `PostToolUse` already done incrementally; finalize here). |
| `RUNNING` | `Stop` hook fires | Output contract fails OR subprocess exit code != 0 | `FAILED` | Write `stage_states[<stage_id>].failed_at` and `failure_reason` to `workflow-state.json`. Audit `stage.fail` to `action-log.jsonl`. Apply retry policy. |
| `RUNNING` | `SessionEnd` hook fires with reason "crash" or absent | — | `CRASHED_RECOVERABLE` | Write `stage_states[<stage_id>].crashed_at` to `workflow-state.json`. Audit `stage.crash` to `action-log.jsonl`. |
| `RUNNING` | Orchestrator liveness watchdog detects hung subprocess (heartbeat stale > 120s OR stdout inactive > 300s OR wall-clock > timeout_seconds) | — | `CRASHED_RECOVERABLE` | Kill subprocess (`os.killpg`). Write `stage_states[<stage_id>].killed_at` and `kill_reason` to `workflow-state.json`. Audit `stage.kill` to `action-log.jsonl`. |
| `FAILED` | Retry policy: `attempts < max_attempts` | — | `PENDING` (retry) | Increment `stage_states[<stage_id>].retry_count`. Audit `stage.retry` to `action-log.jsonl`. Apply backoff delay. |
| `FAILED` | Retry policy: `attempts >= max_attempts` AND `then: escalate` | — | `ESCALATED` | Audit `stage.escalate` to `action-log.jsonl`. Notify human (per `terminal_states.escalate.notify`). |
| `FAILED` | Retry policy: `attempts >= max_attempts` AND `then: fail` | — | `CRASHED_UNRECOVERABLE` | Audit `stage.unrecoverable` to `action-log.jsonl`. Mark pipeline as failed. |
| `COMPLETE` | Next stage per `pipeline.json.stages[<current>].on_success` | Next stage exists | Next stage's `PENDING` | Transition pipeline pointer. Audit `pipeline.advance` to `action-log.jsonl`. |
| `COMPLETE` | `on_success` points to terminal state (`complete`) | — | Pipeline `succeeded` | Archive `workflow-state.json` and `action-log.jsonl` to `archive/<run_id>/`. Audit `pipeline.complete` to `action-log.jsonl`. |
| `CRASHED_RECOVERABLE` | Orchestrator restart detects incomplete output | — | `PENDING` (restart stage with same `idempotency_key`) | Audit `stage.restart_after_crash` to `action-log.jsonl`. |
| `REJECTED` | Downstream stage's input contract rejects | `on_reject.bounce_to` exists AND `bounce_count < max_bounces` | Bounce-to stage's `PENDING` | Increment `stage_states[<bounce_to>].bounce_count`. Audit `stage.bounce` to `action-log.jsonl`. |
| `REJECTED` | `bounce_count >= max_bounces` | `then: escalate` | `ESCALATED` | Audit `stage.escalate_after_bounces` to `action-log.jsonl`. |

**Every transition is expressed generically** — "current stage" and "next stage per `pipeline.json`." The state machine code never references `researcher`, `planner`, etc.

### 6.4 The five-stage worked example

For the example `pipeline.json` (Section 3.5.1), the state machine at startup builds:

```
Stages: [research, plan, implement, review, execute]
Initial state: research.PENDING
Transitions (derived from pipeline.json):
  research.COMPLETE → plan.PENDING
  plan.COMPLETE → implement.PENDING
  implement.COMPLETE → review.PENDING
  review.COMPLETE → execute.PENDING
  review.REJECTED → implement.PENDING (max_bounces: 2)
  execute.COMPLETE → pipeline.succeeded
  Any stage.CRASHED_UNRECOVERABLE → pipeline.failed
  Any stage.ESCALATED → pipeline.escalated
```

**Adding a sixth stage `test`** (per Section 3.5.3's worked example) changes `pipeline.json` to:

```
Stages: [research, plan, implement, test, review, execute]
Transitions:
  implement.COMPLETE → test.PENDING    # was: review.PENDING
  test.COMPLETE → review.PENDING
  ...
```

The state machine's code is unchanged. Only the derived transition table (built from `pipeline.json` at startup) changes.

### 6.5 Atomic / crash-safe write pattern for `workflow-state.json`

**Pattern: write-to-temp-then-rename with fsync.** Verified pattern (Section 9.4 of the research report):

```python
import os, json, tempfile
from pathlib import Path

def atomic_write_state(path: Path, state: dict) -> None:
    """Atomically write workflow state to disk. Crash-safe on POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile in same dir => same filesystem => os.replace is atomic
    fd, tmppath = tempfile.mkstemp(dir=path.parent, prefix=".wf-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(state, sort_keys=True, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())            # 1) persist file contents
        os.replace(tmppath, path)            # 2) atomic rename
        # 3) persist directory entry
        dirfd = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(dirfd)
        finally: os.close(dirfd)
    except BaseException:
        try: os.unlink(tmppath)
        except FileNotFoundError: pass
        raise
```

**Why this pattern:**
- `os.replace` is atomic on POSIX (Python docs: *"this is a POSIX requirement"* — `docs.python.org/3/library/os.html#os.replace`, accessed 2026-08-16).
- `fsync(tempfile)` before rename ensures the file contents are on disk before the rename lands (otherwise a crash after rename but before data flush can leave a zero-length file — the "ext4 zero-length file problem," documented in LWN.net, accessed 2026-08-16).
- `fsync(directory)` after rename ensures the directory entry is durable (otherwise a power loss may roll back the rename).
- Temp file in the same directory as the destination guarantees same-filesystem (required for atomic `os.replace`).

**Windows caveat:** `os.replace` is atomic on the same volume on Windows (uses `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH`), but cross-volume renames fall back to copy+delete which is NOT atomic. The harness assumes same-volume (the workflow-state file lives in the project directory). Recorded as Section 11 risk (LOW).

### 6.6 `workflow-state.json` schema — example

```json
{
  "schema_version": "1.0",
  "pipeline_run_id": "run-2026-08-16-001",
  "pipeline_name": "default-pipeline",
  "pipeline_version": "1.0.0",
  "started_at": "2026-08-16T12:00:00.000Z",
  "last_updated_at": "2026-08-16T12:05:23.456Z",
  "current_stage_id": "implement",
  "pipeline_status": "running",
  "stage_states": {
    "research": {
      "state": "COMPLETE",
      "subagent": "researcher",
      "session_id": "abc-123",
      "started_at": "2026-08-16T12:00:00.000Z",
      "completed_at": "2026-08-16T12:01:30.123Z",
      "retry_count": 0,
      "bounce_count": 0,
      "output_paths": {
        "findings_md": "/home/z/my-project/download/run-2026-08-16-001/research/findings.md",
        "sources_jsonl": "/home/z/my-project/download/run-2026-08-16-001/research/sources.jsonl"
      },
      "recovery_brief_needed": false,
      "recovery_message": null
    },
    "plan": {
      "state": "COMPLETE",
      "subagent": "planner",
      "session_id": "def-456",
      "started_at": "2026-08-16T12:01:35.000Z",
      "completed_at": "2026-08-16T12:03:10.789Z",
      "retry_count": 0,
      "bounce_count": 0,
      "output_paths": {
        "plan_md": "/home/z/my-project/download/run-2026-08-16-001/plan/plan.md"
      },
      "recovery_brief_needed": false,
      "recovery_message": null
    },
    "implement": {
      "state": "RUNNING",
      "subagent": "implementor",
      "session_id": "ghi-789",
      "started_at": "2026-08-16T12:03:15.000Z",
      "completed_at": null,
      "retry_count": 0,
      "bounce_count": 0,
      "output_paths": {},
      "recovery_brief_needed": false,
      "recovery_message": null,
      "heartbeat": {
        "last_beat_at": "2026-08-16T12:05:20.000Z",
        "last_stdout_at": "2026-08-16T12:05:22.000Z"
      }
    },
    "review": {
      "state": "PENDING",
      "subagent": "reviewer",
      "session_id": null,
      "started_at": null,
      "completed_at": null,
      "retry_count": 0,
      "bounce_count": 0,
      "output_paths": {},
      "recovery_brief_needed": false,
      "recovery_message": null
    },
    "execute": {
      "state": "PENDING",
      "subagent": "executor",
      "session_id": null,
      "started_at": null,
      "completed_at": null,
      "retry_count": 0,
      "bounce_count": 0,
      "output_paths": {},
      "recovery_brief_needed": false,
      "recovery_message": null
    }
  },
  "shared_context": {
    "project_conventions": "ESM imports only; no CommonJS",
    "auth_library": "oslo/password"
  },
  "audit_log_head_hash": "c3d4...",
  "compaction_count": 0,
  "last_compaction_at": null
}
```

**Fields:**
- `pipeline_run_id`: stable identifier for this pipeline run. Used in `idempotency_key` derivation.
- `current_stage_id`: the stage currently in `RUNNING` state (or the next `PENDING` stage if none is running).
- `pipeline_status`: `running` | `succeeded` | `failed` | `escalated`.
- `stage_states`: map of stage_id → per-stage state. Every stage in `pipeline.json` has an entry, initialized to `PENDING` at pipeline start.
- `stage_states[<id>].session_id`: the Devin CLI session_id for this stage's invocation. Used by hooks to look up the current stage.
- `stage_states[<id>].output_paths`: the file paths declared in the stage's output contract. Populated by `Stop` on successful completion.
- `stage_states[<id>].recovery_brief_needed` + `recovery_message`: the recovery-brief injection flag (Section 4.6).
- `stage_states[<id>].heartbeat`: written by `PostToolUse` (every tool call updates `last_beat_at`); written by the Orchestrator's stdout-watcher (updates `last_stdout_at`). Used by the liveness watchdog (Section 9.5).
- `shared_context`: live shared state (Section 5.3.4).
- `audit_log_head_hash`: the SHA-256 hash of the last `action-log.jsonl` entry. Anchored here so that tampering with the audit log is detectable by comparing this hash to a recomputed chain head. (Section 9.3.)
- `compaction_count` + `last_compaction_at`: track compaction events for observability.

### 6.7 Idempotency requirements per stage

The brief requires: *"Specify idempotency requirements per stage so a resumed or retried stage can't duplicate side effects."*

**Mechanism: `idempotency_key`.** Each stage invocation has an `idempotency_key` derived from `pipeline_run_id + stage_id + retry_count`. The key is:

1. **Injected into the stage's task prompt** (so the sub-agent knows its identity and can use it in any side-effecting operations — e.g., naming a branch `run-<idempotency_key>-implementation`).
2. **Written to `workflow-state.json.stage_states[<stage_id>].idempotency_key`** (so the Orchestrator can detect duplicate invocations).
3. **Passed to the sub-agent as an environment variable** `ORCHESTRATOR_IDEMPOTENCY_KEY` (so the sub-agent's hooks can read it without parsing the prompt).

**Idempotency rules per stage type:**

| Stage type | Idempotency requirement | Mechanism |
|---|---|---|
| **Read-only** (e.g., Researcher) | No side effects; safe to retry unconditionally. | `idempotency_key` is informational only. |
| **Write-to-disk** (e.g., Planner, Implementor writing to a scratch dir) | Output must be written to a path that includes the `idempotency_key` (e.g., `/tmp/orchestrator-<idempotency_key>/findings.md`). On retry, the same path is overwritten — no duplicate files. | The task prompt instructs the sub-agent to write to `<scratch_dir>/<idempotency_key>/`. The Orchestrator cleans up the scratch dir before retry. |
| **Side-effecting** (e.g., Executor running `git commit`, `terraform apply`) | The sub-agent MUST check for an existing side effect before re-applying (e.g., `git log --grep="<idempotency_key>"` before committing). The task prompt instructs the sub-agent to do this. The `idempotency_key` is included in commit messages, branch names, and tag names so duplicates are detectable. | The task prompt includes: "Before performing any side-effecting action, check whether an action with idempotency key `<idempotency_key>` has already been performed. If so, skip the action and report 'already done'." |

**The Orchestrator's responsibility:** provide the `idempotency_key` and clean up scratch directories before retry. The sub-agent's responsibility (via its task prompt): use the key in side-effecting operations and check for existing effects before re-applying.

### 6.8 Concurrency and locking for state files

**Single-writer assumption.** Only one Orchestrator process should be writing to `workflow-state.json`, `action-log.jsonl`, and `decisions.sqlite` at a time. The harness does NOT support concurrent Orchestrator processes on the same project.

**Advisory file lock to detect accidental concurrent Orchestrators:**

```python
import fcntl, os
from pathlib import Path

class OrchestratorLock:
    def __init__(self, lockfile: Path):
        self.lockfile = lockfile
        self.fd = None

    def __enter__(self):
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.lockfile), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            os.close(self.fd)
            raise RuntimeError(
                f"Another Orchestrator process holds the lock on {self.lockfile}. "
                f"Only one Orchestrator may run per project. "
                f"To force, delete the lockfile (but verify no Orchestrator is running)."
            ) from e
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            # Do NOT delete the lockfile — it contains the PID for debugging
```

**On non-POSIX (Windows):** `fcntl.flock` is not available. Use `msvcrt.locking` or a placeholder file whose existence indicates "locked" (less robust — doesn't auto-release on crash). The harness targets POSIX (Linux/macOS) as primary; Windows support is best-effort (Section 11 risk LOW).

**SQLite concurrency:** WAL mode (Section 5.5.1) supports concurrent readers + 1 writer. The Orchestrator is the only writer. CLI/UI tools that read `decisions.sqlite` for inspection can do so without blocking the Orchestrator.

### 6.9 The Pydantic v2 state model — hand-rolled, no `transitions` library

The `transitions` library (v0.9.3, July 2025) does NOT compose cleanly with Pydantic v2 `BaseModel` (verified via Stack Overflow Q72862604, accessed 2026-08-16 — `Machine.add_model(self)` conflicts with Pydantic's `__init__`). The harness uses a hand-rolled Pydantic v2 model with a config-driven transition table:

```python
from pydantic import BaseModel, Field, model_validator
from typing import Literal

StageState = Literal[
    "PENDING", "RUNNING", "COMPLETE", "FAILED",
    "REJECTED", "CRASHED_RECOVERABLE", "CRASHED_UNRECOVERABLE", "ESCALATED"
]
PipelineStatus = Literal["running", "succeeded", "failed", "escalated"]

class StageStateRecord(BaseModel):
    state: StageState = "PENDING"
    subagent: str
    session_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    retry_count: int = 0
    bounce_count: int = 0
    output_paths: dict[str, str] = {}
    recovery_brief_needed: bool = False
    recovery_message: str | None = None
    heartbeat: dict[str, str] = {}
    idempotency_key: str | None = None

class WorkflowState(BaseModel):
    schema_version: str = "1.0"
    pipeline_run_id: str
    pipeline_name: str
    pipeline_version: str
    started_at: str
    last_updated_at: str
    current_stage_id: str
    pipeline_status: PipelineStatus = "running"
    stage_states: dict[str, StageStateRecord]
    shared_context: dict[str, str] = {}
    audit_log_head_hash: str = "genesis"
    compaction_count: int = 0
    last_compaction_at: str | None = None

    @model_validator(mode="after")
    def _validate_stage_states(self):
        # Every stage in pipeline.json must have a state record
        # current_stage_id must reference an existing stage
        ...
        return self

class StateMachine:
    """Config-driven state machine. Transitions derived from pipeline.json."""
    def __init__(self, pipeline: PipelineConfig, state: WorkflowState):
        self.pipeline = pipeline
        self.state = state

    def can_transition(self, stage_id: str, event: str) -> bool:
        # Look up the transition in the pipeline-derived table
        ...

    def transition(self, stage_id: str, event: str) -> WorkflowState:
        # Apply the transition, update state, return new state
        # Caller is responsible for atomic_write_state() to disk
        ...
```

This is ~80 lines of code, fully config-driven, no external state-machine dependency.

---

## 7. Hook Integration Map

### 7.1 Session-level firing order — for one Devin CLI session's lifecycle

**Verified against `lifecycle-hooks.md` (accessed 2026-08-16).** For a single `devin -p` session running one pipeline stage, the hooks fire in this order:

```
1. SessionStart              (once, at session start; prompt_id is ABSENT)
2. UserPromptSubmit          (once, for the initial --prompt-file prompt; prompt_id is set)
3. [loop, per agent turn:]
   a. PreToolUse             (before each tool call)
   b. PostToolUse            (after each tool call)
   c. PermissionRequest      (only when a permission-gated action is attempted; not every turn)
4. PostCompaction            (whenever compaction triggers — out of band, mid-session; may fire 0 or many times)
5. stop                      (when the agent decides to finish its turn)
6. [if the agent continues after Stop, repeat from 2]
7. SessionEnd                (once, at session end)
```

**Key observations verified from the docs:**
- `SessionStart` fires BEFORE the first `UserPromptSubmit`, and its payload does NOT include `prompt_id` (which is created on the first user prompt).
- `PreToolUse` and `PostToolUse` fire as **pairs** around each tool call. If a turn has multiple tool calls, multiple pairs fire.
- `PermissionRequest` fires only when a permission-gated action is attempted — not every turn. It fires BEFORE `PreToolUse` for the gated action.
- `PostCompaction` fires out-of-band — it can interrupt the loop at any point when the agent's context window fills and compaction triggers. It fires AFTER compaction completes successfully.
- `Stop` fires when the agent decides to finish its turn. The agent may continue after `Stop` if the user submits a new prompt (in `-p` mode, this doesn't happen — `-p` is single-turn; but in interactive mode, it does).
- `SessionEnd` fires once, at the very end.

**For the harness's `-p` mode (single-turn, non-interactive):** the typical sequence is:
```
SessionStart → UserPromptSubmit → (PreToolUse → PostToolUse)* → [PostCompaction?] → Stop → SessionEnd
```

### 7.2 Pipeline-level sequencing — across N stages

The Orchestrator sequences across the pipeline stages defined in `pipeline.json`. For each stage, the Orchestrator:

1. **Transitions the state machine** to `stage.PENDING → stage.RUNNING`.
2. **Spawns the `devin` subprocess** (Section 3.6).
3. **Waits for `SessionEnd`** (not just `Stop`) before considering the stage complete. Why `SessionEnd` and not `Stop`? Because:
   - `Stop` fires when the agent decides to finish its turn. In `-p` mode, `Stop` is immediately followed by `SessionEnd`. But if the agent's `Stop` hook sets `recovery_brief_needed` (Section 4.5), the Orchestrator wants to know whether the session actually ended or whether the agent will continue.
   - `SessionEnd` is the definitive signal that the subprocess is terminating. The Orchestrator waits for `SessionEnd` (or the subprocess's exit, whichever comes first) before extracting the stage's output and validating the output contract.
4. **Extracts the stage's output** by reading the file paths declared in the registry entry's `output_contract` (Section 8).
5. **Validates the output contract** (Section 8). If validation passes, transitions to `stage.COMPLETE`. If validation fails, transitions to `stage.FAILED` and applies the retry policy.
6. **Transitions to the next stage** per `pipeline.json.stages[<current>].on_success`, or to a terminal state if `on_success` is `complete`.
7. **At each handoff, writes to disk:** updates `workflow-state.json` (atomic write), appends to `action-log.jsonl` (hash-chained), and writes any extracted decisions to `decisions.sqlite`.

**What gets written to disk at each handoff:**
- `workflow-state.json`: `stage_states[<current_stage>].state = COMPLETE`, `completed_at`, `output_paths`. `stage_states[<next_stage>].state = PENDING` (if not already). `current_stage_id = <next_stage>`. `last_updated_at` = now.
- `action-log.jsonl`: `stage.complete` event (with output_paths and validation result), `pipeline.advance` event (with from_stage and to_stage).
- `decisions.sqlite`: any decisions extracted from the stage's `PostToolUse` events are already written incrementally; the `Stop` hook finalizes them (writes a `stage_output` decision summarizing the stage's result).

### 7.3 How a stage's post-compaction recovery brief gets built

When `PostCompaction` fires (verified: it fires after compaction completes successfully, with the `summary` field containing the compactor's output), the Orchestrator's `PostCompaction` hook:

1. **Audits the compaction event** to `action-log.jsonl`:
   ```json
   {"seq": N, "ts": "...", "session_id": "...", "prompt_id": "...", "hook_event": "PostCompaction", "stage_id": "...", "payload": {"summary": "..."}, "prev_hash": "...", "hash": "..."}
   ```
2. **Persists the compaction summary** to `decisions.sqlite`:
   ```sql
   INSERT INTO decisions (ts, pipeline_run_id, stage_id, session_id, subagent, decision_type, rationale, body, metadata)
   VALUES (?, ?, ?, ?, ?, 'compaction_summary', ?, ?, ?);
   ```
   The `body` is the compaction summary text (searchable by future stages via FTS5). The `rationale` is a short summary like "Compaction at <timestamp> for stage <stage_id>."
3. **Sets the `recovery_brief_needed` flag** in `workflow-state.json`:
   ```json
   {"stage_states": {"<stage_id>": {"recovery_brief_needed": true, "recovery_message": "Context was compacted; re-injecting workflow state."}}}
   ```
   This is written atomically (Section 6.5).
4. **Returns nothing** (exit 0, empty stdout). Per Section 2.6, `PostCompaction` does NOT support `additionalContext` injection.

**The recovery brief is then built and injected by the next `UserPromptSubmit` hook** (or `SessionStart` if the session was restarted). That hook:

1. **Reads the `recovery_brief_needed` flag and `recovery_message`** from `workflow-state.json`.
2. **Builds the recovery brief** by combining:
   - The `recovery_message`.
   - The current stage's `id`, `subagent` name, and `task_prompt_file` path.
   - A summary of prior stages' outputs (from `workflow-state.json.stage_states[<prior_stage_id>].output_paths` — the Orchestrator reads the first ~500 chars of each output file to include in the brief).
   - The `shared_context` from `workflow-state.json`.
   - A retrieval from `decisions.sqlite` (FTS5 query: the stage_id and subagent name, plus "decision" — returns the top 5 most relevant past decisions for this stage).
3. **Returns the brief** as `hookSpecificOutput.additionalContext`:
   ```json
   {
     "hookSpecificOutput": {
       "hookEventName": "UserPromptSubmit",
       "additionalContext": "RECOVERY BRIEF:\n- You are in stage 'implement' (subagent: implementor).\n- Task prompt: tasks/implement-task.md\n- Prior stage outputs:\n  - research: /path/to/findings.md (first 500 chars: ...)\n  - plan: /path/to/plan.md (first 500 chars: ...)\n- Shared context: {project_conventions: ESM imports only, auth_library: oslo/password}\n- Relevant past decisions:\n  1. [research] Decided to use OAuth 2.0 with PKCE...\n  2. [plan] Decided to implement in src/auth/...\n- Recovery message: Context was compacted; re-injecting workflow state.\n"
     }
   }
   ```
4. **Clears the `recovery_brief_needed` flag** in `workflow-state.json` (atomic write).

**This is the only sanctioned re-injection channel** (per Section 2.6 and Section 4.6).

### 7.4 Per-hook responsibility table

For each of the 8 hooks, the table below specifies: what the Orchestrator does, what memory layers it reads/writes, and what it returns.

#### 7.4.1 `SessionStart`

| Aspect | Detail |
|---|---|
| **When it fires** | Once, at session start. `prompt_id` is ABSENT. |
| **What the Orchestrator does** | 1. Reads `workflow-state.json` to find the stage with `session_id == <payload.session_id>`. If not found, this is a new session — look up the stage from the subprocess invocation context (the Orchestrator passed the stage_id via env var `ORCHESTRATOR_STAGE_ID` to the `devin` subprocess). 2. If the stage's `recovery_brief_needed` flag is set (e.g., this is a resumed session after crash), build the recovery brief (Section 7.3) and return it via `additionalContext`. 3. Audit `SessionStart` to `action-log.jsonl`. |
| **Memory layers READ** | Working (`workflow-state.json` — to find the stage and check `recovery_brief_needed`). Episodic (`action-log.jsonl` — to find the last event for this session, if resuming). Semantic (`decisions.sqlite` — FTS5 query for relevant past decisions, if building a recovery brief). |
| **Memory layers WRITTEN** | Working (`workflow-state.json` — set `stage_states[<stage_id>].session_id` and `started_at`, if not already set). Episodic (`action-log.jsonl` — append `SessionStart` event). |
| **Returns** | If resuming: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<recovery brief>"}}`. Otherwise: nothing (exit 0, empty stdout). |

#### 7.4.2 `UserPromptSubmit`

| Aspect | Detail |
|---|---|
| **When it fires** | Once, for the initial `--prompt-file` prompt (in `-p` mode). `prompt_id` is set. |
| **What the Orchestrator does** | 1. Reads `workflow-state.json` to check `recovery_brief_needed` for the current stage. 2. If set, build the recovery brief (Section 7.3) and return it via `additionalContext`. Clear the flag. 3. Audit `UserPromptSubmit` to `action-log.jsonl`. |
| **Memory layers READ** | Working (`workflow-state.json` — check `recovery_brief_needed`). Semantic (`decisions.sqlite` — FTS5 query for relevant past decisions, if building a brief). |
| **Memory layers WRITTEN** | Working (`workflow-state.json` — clear `recovery_brief_needed` flag, atomic write). Episodic (`action-log.jsonl` — append `UserPromptSubmit` event). |
| **Returns** | If `recovery_brief_needed`: `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "<recovery brief>"}}`. Otherwise: nothing. |

#### 7.4.3 `PreToolUse`

| Aspect | Detail |
|---|---|
| **When it fires** | Before each tool call. Pairs with `PostToolUse`. |
| **What the Orchestrator does** | 1. Audit `PreToolUse` to `action-log.jsonl` (with `tool_name`, `tool_input`). 2. If `tool_name == "exec"` (or another shell-executing tool), check `tool_input.command` against the destructive-command denylist (Section 4.4). If match → return `{"decision": "block", "reason": "<denylist reason>"}` AND exit 2 (belt-and-suspenders). 3. If `tool_name == "exec"` and `tool_input.command` matches a rewrite rule → return `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {"command": "<rewritten command>"}}}`. 4. Otherwise → return nothing (audit only). |
| **Memory layers READ** | None (the denylist is in `policy.json`, not in a memory layer). |
| **Memory layers WRITTEN** | Episodic (`action-log.jsonl` — append `PreToolUse` event, including the decision made). |
| **Returns** | One of: (a) `{"decision": "block", "reason": "..."}` (for denylist matches — cancels the whole turn per Section 2.10, which is the desired behavior for destructive commands), (b) `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {...}}}` (for rewrite rules — lets the agent continue with the rewritten command), (c) nothing (audit only). |

#### 7.4.4 `PostToolUse`

| Aspect | Detail |
|---|---|
| **When it fires** | After each tool call completes. Pairs with `PreToolUse`. |
| **What the Orchestrator does** | 1. Audit `PostToolUse` to `action-log.jsonl` (with `tool_name`, `tool_input`, `tool_response`). 2. Update the heartbeat in `workflow-state.json`: `stage_states[<stage_id>].heartbeat.last_beat_at = now`. Atomic write. 3. If `tool_response.success == false`, optionally inject a correction via `additionalContext` (e.g., "The previous command failed with: <error>. Consider <suggestion>."). 4. If the tool call produced a decision (heuristic: the `tool_name` is `edit` or `write` to a file under the stage's output contract paths, OR the `tool_response.output` contains decision-like text), extract the decision and write it to `decisions.sqlite`. 5. If the tool call produced a shared fact (heuristic: the `tool_response.output` contains a project-level convention), write it to `workflow-state.json.shared_context`. |
| **Memory layers READ** | Working (`workflow-state.json` — to find the current stage and its output contract paths). |
| **Memory layers WRITTEN** | Working (`workflow-state.json` — update heartbeat, update `shared_context`). Episodic (`action-log.jsonl` — append `PostToolUse` event). Semantic (`decisions.sqlite` — insert decision, if extracted). |
| **Returns** | If `tool_response.success == false` and a correction is available: `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "<correction>"}}`. Otherwise: nothing. |

#### 7.4.5 `PermissionRequest`

| Aspect | Detail |
|---|---|
| **When it fires** | When a permission-gated action is attempted. Fires BEFORE `PreToolUse` for the gated action. |
| **What the Orchestrator does** | 1. Audit `PermissionRequest` to `action-log.jsonl`. 2. If `tool_name` is in the always-allow list → return `{"decision": "approve"}`. 3. If `tool_name` is in the always-deny list → return `{"decision": "block", "reason": "..."}`. 4. If the current stage's `human_approval_required` is true → return nothing (exit 0, empty stdout) — Devin CLI falls back to its current permission mode (`normal`), which prompts the human interactively. 5. Otherwise → return `{"decision": "approve"}` (default-allow for non-human-approval stages). |
| **Memory layers READ** | Working (`workflow-state.json` — to find the current stage and check `human_approval_required`). |
| **Memory layers WRITTEN** | Episodic (`action-log.jsonl` — append `PermissionRequest` event, including the decision made). |
| **Returns** | One of: (a) `{"decision": "approve"}`, (b) `{"decision": "block", "reason": "..."}`, (c) nothing (fall through to interactive prompt). |

#### 7.4.6 `Stop`

| Aspect | Detail |
|---|---|
| **When it fires** | When the agent decides to finish its turn. |
| **What the Orchestrator does** | 1. Audit `Stop` to `action-log.jsonl`. 2. Validate the stage's output contract (Section 8): check that all files declared in the output contract exist and are non-empty, and validate their contents against the contract's JSON schema. 3. If validation passes: do nothing (let the agent stop; the `SessionEnd` hook will finalize). Write a `stage_output` decision to `decisions.sqlite` summarizing the stage's result. 4. If validation fails: set `recovery_brief_needed = true` and `recovery_message = "<validation error>"` in `workflow-state.json` (atomic write). Do NOT block (exit 0). The recovery brief will be injected on the next `UserPromptSubmit` (if the agent continues) or on the next stage's `SessionStart` (if the agent stops and the stage is retried). |
| **Memory layers READ** | Working (`workflow-state.json` — to find the current stage and its output contract). |
| **Memory layers WRITTEN** | Working (`workflow-state.json` — set `recovery_brief_needed` and `recovery_message` if validation fails). Episodic (`action-log.jsonl` — append `Stop` event, including validation result). Semantic (`decisions.sqlite` — insert `stage_output` decision on success). Shared (`decisions.sqlite.shared_facts` — insert any shared facts extracted from the stage's output). |
| **Returns** | **NEVER returns `decision: block`** (infinite-loop risk, Section 4.5). Returns nothing (exit 0) in all cases. |

#### 7.4.7 `PostCompaction`

| Aspect | Detail |
|---|---|
| **When it fires** | After context compaction completes successfully. May fire 0 or many times per session. |
| **What the Orchestrator does** | 1. Audit `PostCompaction` to `action-log.jsonl` (with the `summary` field). 2. Persist the compaction summary to `decisions.sqlite` as a `compaction_summary` decision (searchable by future stages via FTS5). 3. Set `recovery_brief_needed = true` and `recovery_message = "Context was compacted; re-injecting workflow state."` in `workflow-state.json` (atomic write). 4. Increment `compaction_count` and update `last_compaction_at` in `workflow-state.json`. 5. Do NOT attempt to inject `additionalContext` (not supported per docs — Section 2.6). |
| **Memory layers READ** | Working (`workflow-state.json` — to find the current stage). |
| **Memory layers WRITTEN** | Working (`workflow-state.json` — set `recovery_brief_needed`, increment `compaction_count`, update `last_compaction_at`). Episodic (`action-log.jsonl` — append `PostCompaction` event). Semantic (`decisions.sqlite` — insert `compaction_summary` decision). |
| **Returns** | Nothing (exit 0, empty stdout). Per Section 2.6, `PostCompaction` does NOT support `additionalContext` injection. |

#### 7.4.8 `SessionEnd`

| Aspect | Detail |
|---|---|
| **When it fires** | Once, at session end. |
| **What the Orchestrator does** | 1. Audit `SessionEnd` to `action-log.jsonl` (with the `reason` field). 2. If `reason` indicates a clean exit ("completed" or similar): mark the stage's `output_paths` in `workflow-state.json` from the contract-declared paths (the `Stop` hook should have already validated these; this is a finalization step). 3. If `reason` indicates a crash ("crash", "killed", or absent): mark the stage as `CRASHED_RECOVERABLE` in `workflow-state.json` (atomic write). 4. The Orchestrator's main loop detects the `SessionEnd` event (via the subprocess's exit or via the hook's audit log) and proceeds with output extraction and state transition. |
| **Memory layers READ** | Working (`workflow-state.json` — to find the current stage). |
| **Memory layers WRITTEN** | Working (`workflow-state.json` — finalize `output_paths` or mark `CRASHED_RECOVERABLE`). Episodic (`action-log.jsonl` — append `SessionEnd` event). |
| **Returns** | Nothing (exit 0, empty stdout). |

---

## 8. Inter-Agent Handoff Contracts

### 8.1 The generic per-stage output contract

Every registered sub-agent must satisfy a **generic output contract** before its stage can transition to `COMPLETE`. The contract is:

1. **The sub-agent writes its output to disk** at one or more file paths declared in the registry entry's `orchestrator.output_contract.schema` (Section 3.3.2). The paths MUST be under a stage-specific scratch directory: `<project>/.devin/orchestrator/runs/<pipeline_run_id>/<stage_id>/`.
2. **Each output file must satisfy its declared schema** (JSON Schema for structured outputs; markdown structure for prose outputs — validated by a lightweight checker, not a full markdown parser).
3. **The `Stop` hook validates the contract** (Section 7.4.6): checks that all declared files exist, are non-empty, and satisfy their schemas.
4. **The output is durable** — written to disk, fsync'd by the sub-agent (the task prompt instructs the sub-agent to ensure durability; the Orchestrator's `PostToolUse` hook can also enforce this by intercepting `write` tool calls and fsyncing).

**Generic contract schema** (the base, extended by each sub-agent's registry entry):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["output_paths", "summary"],
  "properties": {
    "output_paths": {
      "type": "object",
      "description": "Map of output_name → file path. Each path must be under the stage's scratch directory.",
      "additionalProperties": {"type": "string"}
    },
    "summary": {
      "type": "string",
      "description": "A 1-3 sentence summary of what the stage produced, written by the sub-agent. Will be persisted to decisions.sqlite as the rationale of the stage_output decision."
    },
    "decisions_made": {
      "type": "array",
      "description": "Optional. List of key decisions made during this stage, each with a rationale. Persisted to decisions.sqlite.",
      "items": {
        "type": "object",
        "required": ["rationale"],
        "properties": {
          "rationale": {"type": "string"},
          "body": {"type": "string", "description": "Full searchable text"},
          "metadata": {"type": "object"}
        }
      }
    },
    "shared_facts": {
      "type": "array",
      "description": "Optional. Project-level facts discovered during this stage that should be shared with future stages.",
      "items": {
        "type": "object",
        "required": ["fact_key", "fact_value"],
        "properties": {
          "fact_key": {"type": "string"},
          "fact_value": {"type": "string"},
          "rationale": {"type": "string"}
        }
      }
    }
  }
}
```

**The contract file is written by the sub-agent** to `<scratch_dir>/contract.json` at the end of its run. The `Stop` hook reads this file and validates it against the registry entry's `output_contract.schema`.

### 8.2 The per-stage extension mechanism

Each sub-agent's registry entry extends the generic contract with stage-specific fields via the `orchestrator.output_contract.schema` frontmatter field (Section 3.3.2). For example, the Researcher sub-agent's contract might require:

```yaml
orchestrator:
  output_contract:
    schema:
      type: object
      required: [output_paths, summary, findings_md_path, sources_jsonl_path]
      properties:
        findings_md_path:
          type: string
          description: "Path to the findings markdown file."
        sources_jsonl_path:
          type: string
          description: "Path to the sources JSONL file (one source per line)."
        # ... inherits output_paths, summary, decisions_made, shared_facts from generic
```

The `Stop` hook merges the generic contract with the stage-specific schema (using JSON Schema's `allOf`) and validates the sub-agent's `contract.json` against the merged schema.

### 8.3 How the Orchestrator extracts a completed stage's output

The extraction mechanism depends on the registry/invocation design (Section 3.6 — independent `devin` subprocess per stage):

1. **The sub-agent writes its output to the contract-declared paths** during its run (the task prompt instructs it to do so).
2. **The sub-agent writes a `contract.json` file** to `<scratch_dir>/contract.json` at the end of its run, summarizing its output (paths, summary, decisions, shared facts).
3. **The `Stop` hook validates `contract.json`** against the merged schema (Section 8.2).
4. **The `SessionEnd` hook finalizes the output paths** in `workflow-state.json` (atomic write).
5. **The Orchestrator's main loop** (which has been waiting for `SessionEnd` or subprocess exit) detects the completion, reads `workflow-state.json.stage_states[<stage_id>].output_paths`, and uses those paths to build the next stage's task prompt (substituting `from_stage_outputs` references).

**Why this works for any sub-agent (including ones that don't exist yet):** the contract is data (a JSON Schema in the registry entry), not code. A new sub-agent just declares its output contract in its `.md` file's frontmatter; the `Stop` hook validates against it generically. No code changes.

### 8.4 Validation gates between stages

The brief asks: *"can a stage reject and bounce back to an earlier one? How many retries before escalating to a human? What does a rejection actually trigger in the state machine?"*

**Yes, a stage can reject and bounce back.** The mechanism is `on_reject` in `pipeline.json` (Section 3.5.1):

```json
{
  "id": "review",
  "subagent": "reviewer",
  "on_reject": {"bounce_to": "implement", "max_bounces": 2, "then": "escalate"}
}
```

**How rejection works:**

1. The Reviewer stage runs. Its task prompt includes the Implementor's output (via `from_stage_outputs`).
2. The Reviewer's `Stop` hook validates the Reviewer's own output contract (a review report). If the Reviewer's output indicates rejection (heuristic: the review report contains a "REJECT" verdict or fails a schema check for "APPROVE"), the `Stop` hook sets a `rejection` field in `workflow-state.json`:
   ```json
   {"stage_states": {"review": {"rejection": {"target_stage": "implement", "reason": "..."}}}}
   ```
3. The Orchestrator's main loop detects the rejection (the Reviewer's state transitions to `REJECTED`, not `COMPLETE`).
4. The state machine transitions per `on_reject`: if `bounce_count < max_bounces`, transition `implement` to `PENDING` (with `bounce_count` incremented) and re-run it. The Implementor's task prompt is augmented with the rejection reason (injected via `UserPromptSubmit`'s `additionalContext`).
5. If `bounce_count >= max_bounces`, transition to `ESCALATED` (terminal state, notifies human).

**Retries before escalating to a human:**
- **Per-stage retries** (transient failures): governed by `on_failure.retry` in `pipeline.json`. Default: 2 retries before escalating.
- **Bounce retries** (rejection loop): governed by `on_reject.max_bounces`. Default: 2 bounces before escalating.
- **Crash recovery retries**: governed by the retry policy in the registry entry's `orchestrator.retry_policy`. Default: 3 retries for transient crashes before marking `CRASHED_UNRECOVERABLE`.

**What a rejection triggers in the state machine:** the `REJECTED` state (Section 6.2) and the `on_reject` transition (Section 6.3). The rejection reason is persisted in `workflow-state.json` and `action-log.jsonl`, and injected into the bounce-to stage's task prompt via the recovery-brief mechanism (Section 4.6).

### 8.5 The handoff file format

At each stage handoff, the Orchestrator writes a **handoff manifest** to `<scratch_dir>/handoff.json`:

```json
{
  "from_stage": "research",
  "to_stage": "plan",
  "pipeline_run_id": "run-2026-08-16-001",
  "from_stage_output_paths": {
    "findings_md": "/path/to/findings.md",
    "sources_jsonl": "/path/to/sources.jsonl"
  },
  "from_stage_summary": "Researched the auth module; found OAuth 2.0 with PKCE is the standard...",
  "shared_context": {
    "project_conventions": "ESM imports only",
    "auth_library": "oslo/password"
  },
  "rejection": null,
  "ts": "2026-08-16T12:01:30.123Z"
}
```

The next stage's task prompt references this file (via `from_stage_outputs`), and the sub-agent reads it to understand what the prior stage produced. The handoff manifest is also audited to `action-log.jsonl` as a `pipeline.advance` event.

---

## 9. Error Handling & Recovery

### 9.1 Retry policy by failure class

The brief requires: *"Retry policy by failure class (transient vs. logic error vs. environment error) — what auto-retries, what escalates."*

**Three failure classes:**

| Class | Definition | Examples | Auto-retry? | Max attempts | Escalates to |
|---|---|---|---|---|---|
| **Transient** | The failure is caused by a temporary condition that may resolve on retry. | Network timeout, API rate limit, subprocess spawn fails (ENOENT), Devin CLI internal error, OOM kill of the subprocess. | YES | 3 (configurable per stage via `orchestrator.retry_policy.transient.max_attempts`) | `FAILED` → `CRASHED_UNRECOVERABLE` (then `ESCALATED` if `then: escalate`) |
| **Logic error** | The sub-agent produced output, but the output is wrong (fails the output contract or is rejected by a downstream stage). | Researcher wrote findings to the wrong path; Implementor's code doesn't compile; Reviewer rejected the implementation. | NO (immediate escalation to bounce-back or human) | 0 (the bounce mechanism handles re-tries, not the retry policy) | `REJECTED` → bounce-to stage (per `on_reject`); if `max_bounces` exceeded → `ESCALATED` |
| **Environment error** | The failure is caused by the environment (not the sub-agent's logic and not a transient condition). | Disk full, permission denied, FTS5 unavailable, Python version mismatch, Devin CLI not installed. | NO (these require human intervention to fix the environment) | 0 | `FAILED` → `ESCALATED` immediately |

**How the failure class is determined:**
- **Transient:** the subprocess exited non-zero AND the exit code or stderr matches a transient-error pattern (e.g., "rate limit", "timeout", "connection refused"). OR the liveness watchdog killed the subprocess (heartbeat stale). Configurable via `policy.json.transient_error_patterns`.
- **Logic error:** the `Stop` hook's output contract validation failed, OR a downstream stage's input contract validation rejected the output.
- **Environment error:** the Orchestrator's startup checks failed (FTS5 unavailable, Devin CLI not installed, disk full), OR the subprocess spawn failed with an environment-related error (ENOENT for the `devin` binary, EACCES).

**Backoff strategy** (for transient retries):
- **Exponential backoff** (default): `delay = base * 2^attempt`, with `base = 5s` and a cap of 300s. Jitter ±20% to avoid thundering herd.
- **Linear backoff** (configurable): `delay = base * attempt`, with `base = 30s`.
- Configurable per stage via `orchestrator.retry_policy.transient.backoff`.

### 9.2 Dead-letter / escalation path

The brief asks: *"Dead-letter/escalation path for a stage that's stuck or fails repeatedly."*

**Mechanism:** when a stage reaches `ESCALATED` (terminal state), the Orchestrator:

1. **Writes an `escalation` record** to `workflow-state.json`:
   ```json
   {"pipeline_status": "escalated", "escalation": {"stage_id": "implement", "reason": "max_retries_exceeded", "attempts": 3, "last_failure": "...", "ts": "..."}}
   ```
2. **Audits the escalation** to `action-log.jsonl` (hash-chained).
3. **Notifies the human** per `terminal_states.escalate.notify` in `pipeline.json`. Default notification mechanisms:
   - Write a file `<project>/.devin/orchestrator/escalations/<run_id>-<stage_id>.md` with a human-readable summary of the escalation (what stage, what failure, what was attempted, what the output was, what the human should do).
   - Print the escalation summary to the Orchestrator's stdout/stderr.
   - (Optional, Phase 5) send a webhook or desktop notification.
4. **Pauses the pipeline.** The Orchestrator does NOT automatically proceed to the next stage. The human must intervene: either (a) fix the issue and restart the Orchestrator (which will resume from the escalated stage with a fresh retry count), or (b) manually mark the stage as `COMPLETE` with a human-provided output (via a CLI command `orchestrator mark-complete <stage_id> --output-path <path>`), or (c) abort the pipeline (`orchestrator abort <run_id>`).

**There is no automatic dead-letter queue** — the escalation file IS the dead-letter record. The human reads it, decides what to do, and either restarts or aborts.

### 9.3 Tamper-evident audit trail — hash-chaining + external anchor

The brief asks: *"does `action-log.jsonl` need hash-chaining (each entry hashes the previous one) to be genuinely tamper-evident, or is append-only plus file permissions enough?"*

**Answer: hash-chaining is needed; append-only + file permissions is not enough.**

**Threat model** (per NIST SP 800-92, accessed 2026-08-16): the adversary is a same-user process — a malicious or buggy sub-agent that attempts to cover its tracks by editing the audit log. Append-only + `chmod 600` stops other users but NOT same-user processes (the sub-agent runs as the same user as the Orchestrator and has the same file permissions).

**Hash-chaining makes in-place edits detectable:** if an adversary modifies entry `E_i`, the `prev_hash` field of `E_{i+1}` no longer matches `H(E_i)`, and every subsequent entry's `prev_hash` is broken. Verification (Section 5.4) catches this on read.

**But hash-chaining does NOT stop a same-user adversary from rewriting the entire file** (recomputing every `prev_hash` from scratch). To detect that, an **external anchor** is needed:

1. **The `audit_log_head_hash` field in `workflow-state.json`** (Section 6.6) stores the SHA-256 of the last `action-log.jsonl` entry. This is updated on every append. If an adversary rewrites the entire `action-log.jsonl`, they must also rewrite `workflow-state.json` to keep the head hash consistent — but `workflow-state.json` is written atomically (temp + fsync + rename), so a partial rewrite is detectable.
2. **Periodic external anchoring** (optional, Phase 5): every N events (default N=100), the Orchestrator writes the current head hash to an out-of-band location:
   - A git commit to a separate branch (the adversary would need git push permissions to forge it).
   - A separate file owned by a different OS user (if the harness runs under a dedicated user).
   - A notarization service (Certificate Transparency log, a blockchain anchor).
   - For local-first KISS: print the head hash to stdout at every N events, so the human can eyeball it or copy it to a notes file.

**For v1, only mechanism 1 (the `audit_log_head_hash` field) is implemented.** Mechanism 2 is a Phase 5 enhancement. This is recorded as Section 11 risk (MEDIUM): "Hash-chaining detects in-place edits but not full rewrites; the `audit_log_head_hash` anchor in `workflow-state.json` raises the bar but is not cryptographically strong against a same-user adversary with write access to both files."

### 9.4 Liveness / health detection for long-running sessions

The brief asks: *"how does the Orchestrator tell a hung session from one still legitimately working?"*

**Three-layer liveness detection** (belt-and-suspenders, mirroring LangGraph's `TimeoutPolicy` pattern):

1. **Heartbeat file** (every 30s): the `PostToolUse` hook updates `stage_states[<stage_id>].heartbeat.last_beat_at` in `workflow-state.json` on every tool call. If the sub-agent is actively using tools, this updates frequently. The Orchestrator's watchdog checks it every 30s; if `now - last_beat_at > 120s` (4 missed beats), the stage is considered hung.

2. **Stdout inactivity timeout** (300s): the Orchestrator's subprocess watcher reads `proc.stdout` continuously. If no bytes are read for 300s, the stage is considered hung (the agent is either stuck in a long LLM call that hasn't produced output, or has deadlocked). Configurable per stage via `orchestrator.timeout_seconds` (default 300s for the inactivity portion; the overall `timeout_seconds` field is the hard wall-clock cap).

3. **Hard wall-clock cap** (3600s default, configurable per stage via `orchestrator.timeout_seconds`): regardless of activity, kill the subprocess after this duration. This catches "the agent is in an infinite loop but producing output" cases.

**When the watchdog detects a hung session:**
1. Kill the subprocess and its descendants: `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)`. Wait 10s. If still alive, `SIGKILL`.
2. Transition the stage to `CRASHED_RECOVERABLE` (Section 6.3).
3. Audit `stage.kill` to `action-log.jsonl` with the `kill_reason` ("heartbeat_stale" | "stdout_inactive" | "wall_clock_exceeded").
4. Apply the retry policy (transient, since a hung session is treated as transient).

**Why three layers:** heartbeat catches "agent stuck in a long LLM call with no tool use"; stdout inactivity catches "agent stuck in a tool call that's not returning"; wall-clock catches "agent is in an infinite loop producing output but never finishing." No single layer covers all three cases.

---

## 10. Phased Build Plan

**Instructions to Devin CLI. Follow this plan literally, phase by phase. Each phase has a pass/fail checkpoint. Do NOT proceed to the next phase until the current phase's checkpoint passes.**

### Phase 0: Environment setup

**Tasks:**
1. Verify Python 3.11+ is installed: `python --version`.
2. Verify `devin` CLI is installed and is version ≥ 3000.2.17 (required for `session_id`/`prompt_id` in hook payloads): `devin --version`. If the version is older, upgrade: `npm install -g @anthropic/devin-cli` (or whatever the install mechanism is — verify with `devin doctor`).
3. Verify FTS5 is available: run `python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('FTS5 OK')"`. If it fails, install `pysqlite3-binary`: `pip install pysqlite3-binary`.
4. Create the project structure:
   ```
   <project>/.devin/
   ├── agents/                    # sub-agent profile markdown files
   ├── orchestrator/
   │   ├── pipeline.json          # the pipeline definition
   │   ├── policy.json            # the destructive-command denylist
   │   ├── hooks.v1.json          # Devin CLI hook config (or symlink to .devin/hooks.v1.json)
   │   ├── runs/                  # per-run scratch directories
   │   ├── archive/               # completed-run archives
   │   └── escalations/           # escalation files
   ├── hooks.v1.json              # symlink to orchestrator/hooks.v1.json (or the file itself)
   └── config.json                # Devin CLI config (permission-mode defaults; model pinned to SWE-1.6)
   ```
5. Create the Orchestrator's Python package structure:
   ```
   <project>/orchestrator/
   ├── __init__.py
   ├── main.py                    # entry point: asyncio.run(main())
   ├── registry.py                # Registry, RegistryEntry (Pydantic v2 models)
   ├── pipeline.py                # PipelineConfig loader
   ├── state.py                   # WorkflowState, StateMachine (Pydantic v2)
   ├── memory.py                  # atomic_write_state, append_audit, decisions.sqlite helpers
   ├── hooks/                     # the 8 hook scripts (one .py per hook)
   │   ├── session_start.py
   │   ├── user_prompt_submit.py
   │   ├── pre_tool_use.py
   │   ├── post_tool_use.py
   │   ├── permission_request.py
   │   ├── stop.py
   │   ├── post_compaction.py
   │   └── session_end.py
   ├── subprocess_runner.py       # asyncio.create_subprocess_exec wrapper with liveness watchdog
   └── lock.py                    # OrchestratorLock (fcntl.flock)
   ```
6. Install Python dependencies: `pydantic>=2.0`, `pyyaml` (for pipeline.yaml support, optional), `jsonschema` (for contract validation). No other dependencies.

**Pass/fail checkpoint:**
- `python -c "import orchestrator; print('package OK')"` succeeds.
- `devin --version` reports ≥ 3000.2.17.
- FTS5 probe succeeds.
- The project structure exists.

### Phase 1: Registry format and loader

**Tasks:**
1. Implement `RegistryEntry` and `Registry` Pydantic v2 models (Section 3.4.2).
2. Implement `Registry.load(project_agents_dir, user_agents_dir)` — scans both directories, parses YAML frontmatter + markdown body, builds the in-memory registry. User-scoped overrides project-scoped on name collision.
3. Implement frontmatter parsing — either use `python-frontmatter` (PyPI) or a 20-line hand-rolled splitter (preferred for KISS): split on `---\n` boundaries, parse the YAML block with `yaml.safe_load`, keep the rest as the markdown body.
4. Create ONE dummy sub-agent profile at `<project>/.devin/agents/dummy.md`:
   ```markdown
   ---
   name: dummy
   description: A dummy sub-agent for testing the registry. Prints hello and exits.
   allowed-tools: [Bash]
   orchestrator:
     output_contract:
       schema:
         type: object
         required: [output_paths, summary]
         properties:
           output_paths: {type: object}
           summary: {type: string}
     timeout_seconds: 60
   ---
   You are a dummy sub-agent. Run `echo "hello from dummy" > <scratch_dir>/output.txt` and write a contract.json file to <scratch_dir>/contract.json with {"output_paths": {"output": "<scratch_dir>/output.txt"}, "summary": "Said hello"}.
   ```
5. Do NOT create `pipeline.json` yet. Do NOT implement the state machine. Just the registry.

**Pass/fail checkpoint:**
- `python -c "from orchestrator.registry import Registry; r = Registry.load(Path('.devin/agents'), Path('~/.config/devin/agents').expanduser()); print(r.entries)"` prints `{'dummy': RegistryEntry(...)}`.
- The dummy profile's frontmatter parses correctly (name, description, allowed-tools, orchestrator block).
- Adding a second dummy profile (copy `dummy.md` to `dummy2.md`, change the name) and re-running the loader shows both entries.
- Removing `dummy2.md` and re-running shows only `dummy` again.

### Phase 2: Generic state machine on top of the registry

**Tasks:**
1. Implement `PipelineConfig` loader — reads `pipeline.json`, validates against the schema (Section 3.5.1), builds the in-memory stage list and transition table.
2. Implement `WorkflowState` and `StateMachine` Pydantic v2 models (Section 6.9).
3. Implement `StateMachine.can_transition(stage_id, event)` and `StateMachine.transition(stage_id, event)` — applies the transition, returns the new state, but does NOT write to disk (the caller is responsible for `atomic_write_state`).
4. Implement `atomic_write_state(path, state)` (Section 6.5).
5. Implement `OrchestratorLock` (Section 6.8).
6. Create a minimal `pipeline.json` with ONE stage (the dummy sub-agent):
   ```json
   {
     "name": "test-pipeline",
     "version": "1.0.0",
     "stages": [
       {"id": "dummy-stage", "subagent": "dummy", "input": {"task_prompt_file": "tasks/dummy-task.md"}, "on_success": "complete", "on_failure": "fail"}
     ],
     "terminal_states": {"complete": {"status": "succeeded"}, "fail": {"status": "failed"}, "escalate": {"status": "escalated", "notify": "human"}}
   }
   ```
7. Create `tasks/dummy-task.md`: "Run your task as described in your system prompt. Write your output to `<scratch_dir>` (passed via the ORCHESTRATOR_SCRATCH_DIR env var)."

**Pass/fail checkpoint:**
- `python -c "from orchestrator.pipeline import PipelineConfig; p = PipelineConfig.load(Path('.devin/orchestrator/pipeline.json')); print(p.stages)"` prints the stage list.
- `python -c "from orchestrator.state import StateMachine; sm = StateMachine(p, initial_state); sm.transition('dummy-stage', 'start'); print(sm.state)"` transitions `dummy-stage` from `PENDING` to `RUNNING`.
- `atomic_write_state` writes `workflow-state.json` atomically — verify by killing the Python process mid-write and confirming the file is either the old or new version, never corrupted.
- Acquiring the `OrchestratorLock` twice (from two Python processes) fails with a clear error.

### Phase 3: Memory system

**Tasks:**
1. Implement `append_audit(path, payload, prev_hash)` (Section 5.4) — append-only JSONL with SHA-256 hash chain.
2. Implement `verify_audit_chain(path)` — walks the log, recomputes hashes, returns `True` or raises on mismatch.
3. Implement `decisions.sqlite` schema initialization (Section 5.5.1) — create tables, FTS5 virtual tables, triggers, set PRAGMAs.
4. Implement `verify_fts5(conn)` (Section 5.5.2) — probe at startup, fail fast if unavailable.
5. Implement `insert_decision(conn, ...)` and `search_decisions(conn, query, limit=20)`.
6. Implement `insert_shared_fact(conn, ...)` and `search_shared_facts(conn, query, limit=20)`.
7. Implement `atomic_write_state(path, state)` (already done in Phase 2, but verify it's used everywhere state is written).

**Pass/fail checkpoint:**
- Append 10 audit records, run `verify_audit_chain`, confirm it returns `True`.
- Tamper with one record (edit it in place), run `verify_audit_chain`, confirm it raises with a clear error pointing to the tampered record.
- Insert 5 decisions, search for a keyword present in 2 of them, confirm both are returned and ranked by BM25.
- Insert a shared fact, search for it, confirm it's returned.
- `decisions.sqlite` is in WAL mode (`PRAGMA journal_mode` returns `wal`).

### Phase 4: Validate the whole chain against one dummy stage

**Tasks:**
1. Implement the 8 hook scripts (Section 7.4). Each is a standalone Python script that reads JSON from stdin, does its thing, writes JSON to stdout (or exits with a code).
2. Implement `.devin/hooks.v1.json` (Section 2.5) that registers all 8 hook scripts.
3. Implement `subprocess_runner.py` (Section 3.6) — spawns `devin -p --prompt-file <task>` with the right flags, captures stdout/stderr, runs the liveness watchdog.
4. Implement `main.py` — the Orchestrator's main loop:
   - Acquire `OrchestratorLock`.
   - Load registry, pipeline, state.
   - For each stage in the pipeline (starting from `current_stage_id`):
     - Transition to `RUNNING`.
     - Spawn the `devin` subprocess.
     - Wait for `SessionEnd` (or subprocess exit).
     - Extract output, validate contract.
     - Transition to `COMPLETE` or `FAILED`.
     - If `COMPLETE`, advance to the next stage.
     - If `FAILED`, apply retry policy.
5. Run the dummy pipeline: `python -m orchestrator.main`.

**Pass/fail checkpoint:**
- The dummy sub-agent runs, produces `output.txt` and `contract.json` in its scratch directory.
- `workflow-state.json` shows `dummy-stage.state = COMPLETE` with the correct `output_paths`.
- `action-log.jsonl` contains `SessionStart`, `UserPromptSubmit`, `PreToolUse` (for the `echo` command), `PostToolUse`, `Stop`, `SessionEnd` events, all hash-chained correctly.
- `decisions.sqlite` contains a `stage_output` decision with the dummy's summary.
- `verify_audit_chain` returns `True`.

### Phase 5 (CRITICAL checkpoint): Register a second dummy stage using only the registry — no code change

**Tasks:**
1. Create `<project>/.devin/agents/dummy2.md` (a second dummy sub-agent, similar to `dummy.md` but with a different name and output).
2. Edit `<project>/.devin/orchestrator/pipeline.json` to add a second stage:
   ```json
   {
     "stages": [
       {"id": "dummy-stage", "subagent": "dummy", ..., "on_success": "dummy-stage-2", ...},
       {"id": "dummy-stage-2", "subagent": "dummy2", "input": {"task_prompt_file": "tasks/dummy2-task.md", "from_stage_outputs": ["dummy-stage"]}, "on_success": "complete", "on_failure": "fail"}
     ]
   }
   ```
3. Create `tasks/dummy2-task.md`.
4. Run `python -m orchestrator.main` again. DO NOT change any code in the `orchestrator/` package.

**Pass/fail checkpoint:**
- The Orchestrator picks up `dummy2` from the registry (no code change).
- The pipeline runs both stages in sequence: `dummy-stage` → `dummy-stage-2`.
- `dummy-stage-2`'s task prompt includes the output path from `dummy-stage` (via `from_stage_outputs`).
- `workflow-state.json` shows both stages as `COMPLETE`.
- `action-log.jsonl` contains events for both stages.
- `decisions.sqlite` contains `stage_output` decisions for both stages.

**If this checkpoint passes, the brief's core requirement is met: "adding a sixth agent must be possible by changing configuration or data, not by editing the Orchestrator's code."**

### Phase 6 (CRITICAL checkpoint): Kill the harness mid-run, restart, confirm it resumes

**Tasks:**
1. Start the dummy pipeline: `python -m orchestrator.main`.
2. While `dummy-stage` is running (after `SessionStart` but before `Stop`), kill the Orchestrator process: `Ctrl+C` or `kill <orchestrator_pid>`.
3. Verify `workflow-state.json` shows `dummy-stage.state = RUNNING` (or `CRASHED_RECOVERABLE` if the `SessionEnd` hook fired with a crash reason).
4. Restart the Orchestrator: `python -m orchestrator.main`.
5. The Orchestrator should detect the incomplete stage and resume it (transition to `PENDING` with the same `idempotency_key`, re-spawn the `devin` subprocess, re-run the stage).

**Pass/fail checkpoint:**
- The Orchestrator resumes from the correct stage (not from the beginning).
- `action-log.jsonl` is intact (no corruption from the kill), and `verify_audit_chain` returns `True`.
- The resumed stage produces the same output (or, if the stage is non-idempotent, the `idempotency_key` mechanism prevents duplicate side effects — Section 6.7).
- `decisions.sqlite` is intact (no corruption from the kill — WAL mode + `synchronous=FULL` ensures this).
- The pipeline completes successfully after the restart.

**If this checkpoint passes, the brief's core requirement is met: "the harness survives context compaction and crashes without losing the workflow."**

### Phase 7: Register the real 5-stage pipeline

**Tasks:**
1. Create the 5 real sub-agent profiles: `<project>/.devin/agents/researcher.md`, `planner.md`, `implementor.md`, `reviewer.md`, `executor.md`. Each with its own system prompt (the prompt content is out of scope for this spec — the implementer writes them), `allowed-tools`, and `orchestrator.output_contract.schema`. (No `model` field — all run on SWE-1.6 per Section 11.14.)
2. Create the 5 task prompt files: `tasks/research-task.md`, `plan-task.md`, `implement-task.md`, `review-task.md`, `execute-task.md`.
3. Replace `pipeline.json` with the 5-stage pipeline (Section 3.5.1).
4. Run `python -m orchestrator.main`.

**Pass/fail checkpoint:**
- All 5 stages run in sequence.
- Each stage's output contract is validated.
- `workflow-state.json` shows all 5 stages as `COMPLETE`.
- The pipeline reaches `pipeline.succeeded`.

### Phase 8 (optional): Hot-reload, ACP integration, parallel stages

**Tasks (each is independent, pick as needed):**
1. **Hot-reload:** add `watchfiles.awatch(<project>/.devin/agents/)` to the Orchestrator's event loop. On file change, re-scan, rebuild the registry, atomically swap, log to `action-log.jsonl`.
2. **ACP integration:** replace `devin -p --prompt-file` with `devin acp` (JSON-RPC over stdio) for richer programmatic control. Speak ACP from the Orchestrator, receive structured events, interrupt/steer mid-flight.
3. **Parallel stages:** extend `pipeline.json` schema with `parallel_slices` field; spawn N subprocesses per stage with distinct `idempotency_key`s; merge outputs.
4. **External audit anchor:** every N=100 audit events, write the head hash to a git commit on a separate branch, or print to stdout for human eyeballing.

**Pass/fail checkpoint (per task):**
- Hot-reload: add a new sub-agent profile while the Orchestrator is running; confirm the next stage picks it up without a restart.
- ACP: the Orchestrator receives structured `PreToolUse` events as JSON-RPC messages (not as hook script invocations).
- Parallel: 3 Implementor instances run concurrently, each with a distinct `session_id` and `idempotency_key`; outputs are merged.
- External anchor: after 100 audit events, the head hash is anchored externally.

---

## 11. Open Questions & Risks

Each item is rated **CRITICAL / HIGH / MEDIUM / LOW** and states what decision it blocks.

### 11.1 CRITICAL — `decision: block` scope on `PreToolUse` is not officially documented

**Risk:** The `oraios/serena#1757` finding (accessed 2026-08-16) that `decision: block` cancels the WHOLE turn (not just the single tool call) is empirically verified against `devin 3000.2.17` but is NOT explicitly stated in Devin CLI's official docs. If a future Devin CLI release changes this behavior (e.g., to match Claude Code's per-call `deny` semantics), the enforcement model in Section 4 would need revision.

**Decision it blocks:** The enforcement policy (Section 4) assumes whole-turn scope. If Devin CLI changes to per-call scope, the policy can be relaxed (block more liberally) but the current design is safe under either interpretation (block is reserved for destructive commands where whole-turn abort is desirable).

**Mitigation:** Add a startup self-test that spawns a `devin -p` session, registers a `PreToolUse` hook that blocks `echo test`, runs `echo test`, and verifies that the whole turn is cancelled (subprocess exits non-zero with a specific error). Pin the test to the verified Devin CLI version.

### 11.2 CRITICAL — `PostCompaction` cannot inject `additionalContext` (per docs)

**Risk:** Section 2.6 documents that `PostCompaction` is NOT in Devin CLI's list of hooks that support `additionalContext` injection. The harness works around this by setting a `recovery_brief_needed` flag and injecting on the next `UserPromptSubmit` or `SessionStart`. But this depends on Devin CLI firing `UserPromptSubmit` AFTER compaction (in `-p` mode, there's only one user prompt — the initial one — so if compaction happens mid-turn, there may be no subsequent `UserPromptSubmit` to inject on).

**Decision it blocks:** The entire post-compaction recovery mechanism (Sections 4.6, 7.3).

**Mitigation:** Test empirically in Phase 4. Run a `devin -p` session with a task large enough to trigger compaction, register a `PostCompaction` hook that sets the flag, and observe whether `UserPromptSubmit` fires again after compaction. If it does NOT, the recovery brief must be injected via `SessionStart` of the NEXT stage (which means the compacted stage's agent continues amnesiac for the rest of its turn — acceptable if the stage is near completion, problematic if it's mid-stage). If this is a problem, migrate to `devin acp` (Phase 8) where the Orchestrator can inject context programmatically mid-turn.

### 11.3 HIGH — Output format chosen without explicit user confirmation

**Risk:** The user did not answer the output-format question in the AskUserQuestion round. I made the defensible call to produce markdown only. If the user actually wanted a PDF or both formats, this deliverable is incomplete.

**Decision it blocks:** None — the markdown spec is sufficient for Devin CLI to consume. If the user wants a human-readable PDF, it can be generated from the markdown in a follow-up.

**Mitigation:** Surface this assumption explicitly in the summary message to the user.

### 11.4 HIGH — Compaction token threshold is not documented

**Risk:** Devin CLI's docs do not publish the exact token threshold at which automatic compaction triggers. The brief specifies "~120K tokens" as the trigger. If Devin CLI's actual threshold differs, the harness's compaction policy (compact only between stages) may not be enforceable — Devin CLI may compact mid-stage regardless.

**Decision it blocks:** The compaction policy (Section 4.3, `PostCompaction` hook behavior).

**Mitigation:** The harness cannot prevent mid-stage compaction (it's Devin CLI's internal behavior). The `PostCompaction` hook handles mid-stage compaction by setting `recovery_brief_needed` and relying on the next `UserPromptSubmit` (or `SessionStart` of the next stage) to re-inject. The "~120K tokens" target is a planning heuristic for sizing task prompts, not an enforcement mechanism.

### 11.5 HIGH — Concurrency limits are not documented

**Risk:** Devin CLI does not document a max concurrent sessions per user. The harness's `asyncio.Semaphore` (default 4 concurrent sub-agent sessions) is a guess. If Devin CLI has a lower undocumented limit, parallel stages (Phase 8) could fail.

**Decision it blocks:** Parallel stage execution (Phase 8).

**Mitigation:** For v1 (sequential pipeline), this is not a problem. For Phase 8 (parallel stages), test empirically: spawn 1, 2, 4, 8 concurrent `devin -p` sessions and observe whether they all complete or some fail with a concurrency error.

### 11.6 MEDIUM — FTS5 may prove insufficient for paraphrased queries

**Risk:** FTS5 keyword search with BM25 ranking is sufficient for keyword-rich decision text (verified by OpenClaw, Hermes, DeerFlow). But if sub-agents ask questions in paraphrased natural language (e.g., "how did we handle the auth bug" matching a decision titled "OAuth token refresh logic"), FTS5 may miss relevant decisions.

**Decision it blocks:** Semantic memory retrieval quality (Section 5.3.3).

**Mitigation:** The upgrade path is `sqlite-vec` hybrid (FTS5 + vector search, weighted 0.7×vector + 0.3×BM25), which stays single-file and KISS. Defer to Phase 8 if retrieval quality is observed to be insufficient in Phase 7.

### 11.7 MEDIUM — Hash-chaining does not stop full-rewrite attacks

**Risk:** Section 9.3 documents that hash-chaining detects in-place edits but not full rewrites by a same-user adversary. The `audit_log_head_hash` anchor in `workflow-state.json` raises the bar but is not cryptographically strong.

**Decision it blocks:** Tamper-evidence claims for `action-log.jsonl`.

**Mitigation:** For v1, accept the limitation (the threat model is a buggy sub-agent, not a determined adversary). For Phase 8, add external anchoring (git commit, separate OS user, notarization service).

### 11.8 MEDIUM — `transitions` library does not compose with Pydantic v2

**Risk:** Section 6.9 documents that the `transitions` library (v0.9.3) does not work cleanly with Pydantic v2 `BaseModel` (verified via Stack Overflow Q72862604, accessed 2026-08-16). The harness uses a hand-rolled state machine instead. If the state machine needs to grow more complex (nested states, history, async actions), the hand-rolled approach may become unwieldy.

**Decision it blocks:** Future state machine complexity.

**Mitigation:** The hand-rolled state machine is ~80 lines and covers all v1 requirements. If complexity grows, migrate to `python-statemachine` 3.x (v3.2.1, August 2026 — actively maintained, Pydantic-friendly per its migration guide). The migration is a drop-in replacement of the `StateMachine` class.

### 11.9 MEDIUM — Windows atomicity is best-effort

**Risk:** Section 6.5 documents that `os.replace` is atomic on POSIX (guaranteed) but only best-effort on Windows (cross-volume renames fall back to copy+delete). The harness assumes same-volume (workflow-state file in the project directory).

**Decision it blocks:** Windows support.

**Mitigation:** For v1, target POSIX (Linux/macOS) as primary. Document the Windows limitation. If Windows support is needed, use the `atomicwrites` library (PyPI) which handles the Windows-specific `NtSetInformationFile` call.

### 11.10 LOW — Pipeline schema is a strict sequence, not a DAG

**Risk:** Section 3.5.2 documents that v1 uses a strict sequence with conditional branches. Parallel stages, conditional fan-out, and cyclic merge points are out of scope.

**Decision it blocks:** Complex pipeline topologies.

**Mitigation:** The strict-sequence design covers the 5-stage example and most realistic pipelines. For complex topologies, extend `stages` to `nodes` + `edges` (DAG) in v2 — the state machine and registry loader are designed so this extension requires changes to the pipeline schema and transition table, not to the Orchestrator's core loop.

### 11.11 LOW — `max_concurrent_instances` is declared but not exercised in v1

**Risk:** Section 3.7 declares `max_concurrent_instances` in the registry schema but defaults to 1 and does not exercise parallel execution in v1.

**Decision it blocks:** Parallel stage execution.

**Mitigation:** The field is forward-compatible. Phase 8 adds the `parallel_slices` pipeline field to exercise it.

### 11.12 LOW — Hot-reload is deferred to Phase 5

**Risk:** Section 3.8 defers hot-reload to Phase 5. For v1, adding a new sub-agent requires restarting the Orchestrator.

**Decision it blocks:** Zero-downtime sub-agent additions.

**Mitigation:** Restart-on-change is acceptable for a local dev tool. Phase 5 adds `watchfiles.awatch` for hot-reload.

### 11.13 LOW — Hot-reload is deferred to Phase 5

(Covered above in Section 11.12.)

### 11.14 Model pinned to SWE-1.6 — user decision

**Status:** User decision (not an assumption). Recorded 2026-08-16.

**Decision:** All sub-agents run on Devin CLI's default subagent model (SWE-1.6). Model switching is out of scope.

**Consequences:**
- The `model` frontmatter field is documented in Section 3.3.1 for completeness but marked "NOT USED by this harness."
- The `RegistryEntry` Pydantic model (Section 3.4.2) omits the `model` field.
- The `devin` subprocess invocation (Section 3.6) does NOT pass `--model`.
- The project's `.devin/config.json` (Section 10, Phase 0) pins the model to SWE-1.6.
- The worked example in Section 3.5.3 (the `tester` sub-agent) does NOT set `model: sonnet`.
- The dummy profile in Phase 1 does NOT set `model: haiku`.
- The 5 real sub-agent profiles in Phase 7 do NOT set `model`.

**Reversibility:** If model switching becomes a requirement later, adding it back is straightforward:
1. Add `model: str | None = None` to `RegistryEntry`.
2. Extract `model` from the frontmatter in `Registry.load()`.
3. Add `"--model", registry_entry.model` to the subprocess `cmd` in Section 3.6 (only if non-None).
4. Remove the SWE-1.6 pin from `.devin/config.json`.

No other code or schema changes are needed. The state machine, hook scripts, memory system, and pipeline schema are model-agnostic.

### 11.15 Assumptions recorded on the user's behalf

Per the brief's instruction: *"where this brief is ambiguous, make the most defensible call, record the assumption in Section 11, and continue."*

1. **Output format: markdown only.** The user did not answer the output-format question. Markdown is the agent-native format (zero parsing overhead for Devin CLI), an 80+ page deep-dive is easier to produce iteratively as markdown than PDF, and the brief itself was delivered as markdown. Assumption recorded.
2. **Spec posture: brief is authoritative.** The user confirmed this. The 8 hooks are the target spec; build them as specified, shimming where Devin CLI natively lacks them (in practice, no shimming is needed — Devin CLI supports all 8).
3. **Sourcing: Devin CLI docs only.** The user confirmed this. Claude Code is NOT cited as a source for hook payloads/semantics. Where Devin's docs cross-reference Claude Code (and they do — Devin explicitly states its hooks are "the same convention used by Claude Code"), that cross-reference is preserved as Devin's own statement.
4. **Length: deep-dive (80+ pages).** The user confirmed this. The spec is comprehensive.
5. **Field name corrections:** The brief uses `modifiedInput`, `permissionDecision`, `cwd`, `transcript_path`, and the flags `--output-format json`, `--agent`, `--initial-prompt`, `--no-input`, `--headless`, `--max-turns`. These are Claude Code conventions, NOT Devin CLI's. The spec uses Devin CLI's actual field names (`updatedInput`, `decision`, `DEVIN_PROJECT_DIR`) and actual CLI flags (`-p`/`--print`, `--prompt-file`, `--permission-mode`, `--sandbox`, `--export`, `--respect-workspace-trust false`). The `--model` flag is intentionally omitted — all sub-agents run on SWE-1.6 (Section 11.14). This is a defensible call — using the wrong field names would break the harness.
6. **`decision: block` scope:** The brief states that JSON `{"decision":"block","reason":"..."}` is "more expressive" than exit code 2. Empirically (oraios/serena#1757), both have the same scope (whole-turn block in Devin). The spec uses block ONLY for destructive commands where whole-turn abort is desired, and uses `updatedInput` for "nudge and let continue" semantics. This is a defensible call given the verified behavior.
7. **PostCompaction re-injection:** The brief states that `PostCompaction` "reloads state from disk and re-injects a recovery brief." Per Devin CLI's docs, `PostCompaction` does NOT support `additionalContext` injection. The spec works around this by setting a flag and injecting on the next `UserPromptSubmit` or `SessionStart`. This is a defensible call given the docs — the alternative (assuming PostCompaction can inject) would risk the recovery brief being silently dropped.

8. **Model pinned to SWE-1.6 (user decision, not assumption):** The user explicitly stated (2026-08-16) that the deployment uses only SWE-1.6 and model-switching functions are not pertinent. Accordingly: the `model` frontmatter field is documented for completeness but NOT read by the Orchestrator; the `RegistryEntry` Pydantic model omits the `model` field; the `--model` CLI flag is NOT passed to the `devin` subprocess; the project's `.devin/config.json` pins the model to SWE-1.6. If model switching becomes a requirement later, adding it back is a one-line change to `RegistryEntry` and one flag to the subprocess invocation (Section 11.14).

---

## 12. Sources

All sources accessed 2026-08-16 unless otherwise noted.

### 12.1 Devin CLI primary documentation

1. Hooks overview — `https://docs.devin.ai/cli/extensibility/hooks/overview.md`
2. Lifecycle hooks deep-dive — `https://docs.devin.ai/cli/extensibility/hooks/lifecycle-hooks.md`
3. CLI command reference — `https://docs.devin.ai/cli/reference/commands.md`
4. Extensibility overview — `https://docs.devin.ai/cli/extensibility/index.md`
5. Configuration — `https://docs.devin.ai/cli/extensibility/configuration.md`
6. Subagents — `https://docs.devin.ai/cli/subagents.md`
7. Changelog — `https://docs.devin.ai/cli/changelog/stable.md`
8. Quickstart — `https://docs.devin.ai/cli.md`
9. Essential commands — `https://docs.devin.ai/cli/essential-commands.md`
10. Cascade Hooks (Devin Desktop — separate product) — `https://docs.devin.ai/desktop/cascade/hooks.md`
11. API reference (Devin Cloud — separate product) — `https://docs.devin.ai/api-reference/overview.md`
12. Documentation index — `https://docs.devin.ai/llms.txt`

### 12.2 Independent community corroboration (Devin CLI hooks)

13. `oraios/serena#1757` — Serena Devin CLI integration PR; empirically verified payload schema and `decision:block` whole-turn-scope caveat against `devin 3000.2.17`. `https://github.com/oraios/serena/issues/1757`
14. `rtk-ai/rtk#3143` — RTK Devin integration feature request; confirms hook shape matches Claude Code/Cursor. `https://github.com/rtk-ai/rtk/issues/3143`
15. `paperclipai/paperclip#11109` — Adapter request confirming headless mode and structured output parsing. `https://github.com/paperclipai/paperclip/issues/11109`
16. `TheColliery/CoalHearth` — Real `.devin/hooks.v1.json` example. `https://github.com/TheColliery/CoalHearth/blob/main/platform-configs/hooks/devin-cli-hooks.json`
17. Leaked Devin CLI system prompt — confirms hooks are part of the shipped agent. `https://github.com/asgeirtj/system_prompts_leaks/blob/main/Misc/devin-cli.md`
18. Cognition launch blog — "Run multiple agents against the same codebase." `https://cognition.com/blog/devin-for-terminal`
19. Fast.io community guide — "Hooks in Devin CLI allow teams to configure execution policies." `https://fast.io/resources/devin-ai-terminal`
20. AI @ Sulat.com — "The hook format is compatible with Claude Code hooks." `https://ai.sulat.com/devin-cli-beyond-the-defaults-3487abea6596`
21. Blake Crosley — Third-party confirmation Claude Code has 31 hook events. `https://blakecrosley.com/blog/claude-code-hooks-explained`

### 12.3 Claude Code (for comparison only — NOT cited as a source for hook payloads)

22. Claude Code hooks reference (31 events) — `https://code.claude.com/docs/en/hooks`
23. Claude Code headless mode — `https://code.claude.com/docs/en/headless.md`
24. Claude Code subagents — `https://code.claude.com/docs/en/sub-agents`

### 12.4 Memory systems research

25. Letta (formerly MemGPT) — `https://github.com/letta-ai/letta`
26. Mem0 — `https://github.com/mem0ai/mem0` and `https://mem0.ai`
27. Zep — `https://github.com/getzep/zep` and `https://getzep.com`
28. Graphiti (Zep's OSS graph engine) — `https://github.com/getzep/graphiti`
29. LangGraph — `https://github.com/langchain-ai/langgraph`
30. LangGraph fault tolerance blog — `https://www.langchain.com/blog/fault-tolerance-in-langgraph`
31. LangGraph `TimeoutPolicy` reference — `https://reference.langchain.com/python/langgraph/types/TimeoutPolicy`
32. AutoGen — `https://github.com/microsoft/autogen` and `https://microsoft.github.io/autogen`
33. AutoGen v0.4 announcement — `https://www.microsoft.com/en-us/research/blog/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness`
34. DeerFlow (ByteDance) — `https://github.com/bytedance/deer-flow`
35. Hermes Agent — `https://github.com/NousResearch/hermes-agent`
36. Hermes Agent #487 (hash-chain audit proposal) — `https://github.com/NousResearch/hermes-agent/issues/487`
37. OpenClaw Memory — OpenClaw repo (pure stdlib + SQLite FTS5)
38. memweave (FTS5 + sqlite-vec hybrid) — memweave repo
39. WorkOS audit harness — WorkOS docs (JSONL audit plugins for 6 coding agents)
40. CopilotKit #2059 (LangGraph timeout issue) — `https://github.com/CopilotKit/CopilotKit/issues/2059`

### 12.5 Registry / plugin patterns research

41. Claude Code subagents (markdown profiles, `.claude/agents/`) — `https://code.claude.com/docs/en/sub-agents`
42. Devin CLI subagents — `https://docs.devin.ai/cli/subagents.md`
43. Apache Airflow DAGs (file-based auto-discovery) — `https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html`
44. Airflow DAG file processing — `https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/dagfile-processing.html`
45. Airflow config reference (`min_file_process_interval`) — `https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html`
46. Airflow DagBag API — `https://airflow.apache.org/docs/apache-airflow/2.11.0/_api/airflow/models/dagbag/index.html`
47. Prefect flows — `https://docs.prefect.io/v3/concepts/flows`
48. Prefect write-and-run — `https://docs.prefect.io/v3/how-to-guides/workflows/write-and-run`
49. Celery tasks — `https://docs.celeryq.dev/en/main/userguide/tasks.html`
50. Celery autodiscover — `https://docs.celeryq.dev/en/stable/reference/celery.html`
51. Dagster definitions — `https://docs.dagster.io/api/dagster/definitions`
52. Dagster components (`DefsFolderComponent`) — `https://docs.dagster.io/api/dagster/components`
53. Dagster migrating definitions — `https://docs.dagster.io/guides/build/projects/moving-to-components/migrating-definitions`
54. Dramatiq — `https://dramatiq.io/cookbook.html`
55. Mage core abstractions — `https://docs.mage.ai/design/core-abstractions`
56. LangGraph graph API — `https://docs.langchain.com/oss/python/langgraph/graph-api`
57. LangGraph `StateGraph` — `https://reference.langchain.com/python/langgraph/graph/state/StateGraph`
58. LangGraph supervisor — `https://reference.langchain.com/python/langgraph-supervisor`
59. AutoGen code executors — `https://microsoft.github.io/autogen/0.2/docs/tutorial/code-executors`
60. CrewAI crews — `https://docs.crewai.com/v1.15.6/en/concepts/crews`
61. CrewAI tasks — `https://docs.crewai.com/v1.15.14/en/concepts/tasks`
62. OpenAI Swarm — `https://github.com/openai/swarm`
63. OpenAI Agents SDK — `https://openai.github.io/openai-agents-python/agents/`
64. Meltano plugins — `https://docs.meltano.com/concepts/plugins`
65. Meltano plugin definition syntax — `https://docs.meltano.com/reference/plugin-definition-syntax`
66. Singer spec — `https://hub.meltano.com/singer/spec`
67. Singer — `https://www.singer.io`
68. pytest writing plugins — `https://docs.pytest.org/en/stable/how-to/writing_plugins.html`
69. pluggy — `https://github.com/pytest-dev/pluggy`
70. pluggy API — `https://pluggy.readthedocs.io/en/stable/api_reference.html`
71. `importlib.metadata` — `https://docs.python.org/3/library/importlib.metadata.html`
72. `importlib_metadata` (backport) — `https://pypi.org/project/importlib-metadata`
73. CPython #88412 (entry_points API change) — `https://github.com/python/cpython/issues/88412`
74. watchfiles — `https://github.com/samuelcolvin/watchfiles` and `https://watchfiles.helpmanual.io`
75. watchfiles on PyPI — `https://pypi.org/project/watchfiles`
76. uvicorn settings — `https://uvicorn.dev/settings`
77. Hot-reload in Python — `https://pydevtools.com/handbook/explanation/how-does-hot-reloading-work-in-python`
78. gunicorn #2339 (`--reload` with UvicornWorker) — `https://github.com/benoitc/gunicorn/issues/2339`
79. pluggy case study — `https://eli.thegreenplace.net/2026/plugins-case-study-pluggy`

### 12.6 Crash safety / audit / liveness research

80. Python `os.replace` — `https://docs.python.org/3/library/os.html#os.replace`
81. Linux `rename(2)` — `https://man7.org/linux/man-pages/man2/rename.2.html`
82. LWN: "Ensuring data reaches disk" — `https://lwn.net/Articles/457667/`
83. LWN: "Delayed allocation and the zero-length file problem" — `https://lwn.net/Articles/323169/`
84. Alexander Larsson: "ext4 vs fsync, my take" — `https://blogs.gnome.org/alexl/2009/03/16/ext4-vs-fsync-my-take/`
85. Stack Exchange: filesystem fsync requirements — `https://unix.stackexchange.com/questions/464382/`
86. "The syscall I forgot: directory fsync" — `https://aalhour.com/posts/beachdb-the-syscall-i-forgot/`
87. "Crash Consistency: fsync(), rename(), and Durable Writes" — `https://0xkiire.com/crash-consistency-fsync-rename/`
88. `atomicwrites` on PyPI — `https://pypi.org/project/atomicwrites/`
89. `atomicwrites` docs — `https://python-atomicwrites.readthedocs.io/en/latest/`
90. CPython #8828 (atomic rename) — `https://bugs.python.org/issue8828`
91. Python discussion on `atomicwrite` in stdlib — `https://discuss.python.org/t/adding-atomicwrite-in-stdlib/11899`
92. Pydantic v2 serialization — `https://pydantic.dev/docs/validation/2.9/concepts/serialization`
93. Python `os.fsync` — `https://docs.python.org/3/library/os.html#os.fsync`
94. POSIX `write(3p)` — `https://man7.org/linux/man-pages/man3/write.3p.html`
95. Linux `write(2)` — `https://man7.org/linux/man-pages/man2/write.2.html`
96. "Appending to a log: an introduction to the Linux dark arts" — `https://www.pvk.ca/Blog/2021/01/22/appending-to-a-log-an-introduction-to-the-linux-dark-arts/`
97. Kernel bug #55651 (O_APPEND atomicity edge case) — `https://bugzilla.kernel.org/show_bug.cgi?id=55651`
98. Python `open()` — `https://docs.python.org/3/library/functions.html#open`
99. "Are Files Appends Really Atomic?" — `https://www.notthewizard.com/2014/06/17/are-files-appends-really-atomic/`
100. APUE Ch.3 notes on O_APPEND — `https://notes.shichao.io/apue/ch3/`
101. RFC 6962 (Certificate Transparency) — `https://www.rfc-editor.org/info/rfc6962`
102. RFC 9162 (Certificate Transparency v2.0) — `https://datatracker.ietf.org/doc/html/rfc9162`
103. Let's Encrypt RFC 6962 EOL — `https://letsencrypt.org/2025/08/14/rfc-6962-logs-eol/`
104. "How CT Works" — `https://certificate.transparency.dev/howctworks/`
105. AWS CloudTrail log file integrity validation — `https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html`
106. AWS CloudTrail digest file structure — `https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-digest-file-structure.html`
107. Bitcoin block chain reference — `https://developer.bitcoin.org/reference/block_chain.html`
108. Hyperledger Fabric ledger — `https://hyperledger-fabric.readthedocs.io/fa/latest/ledger.html`
109. NIST SP 800-92 (Guide to Computer Security Log Management) — `https://csrc.nist.gov/pubs/sp/800/92/final`
110. NIST SP 800-92r1 draft — `https://csrc.nist.gov/pubs/sp/800/92/r1/ipd`
111. Tamper-evident audit log tutorial — `https://dev.to/veritaschain/building-a-tamper-evident-audit-log-with-sha-256-hash-chains-zero-dependencies-h0b`
112. Hermes Agent #487 (cryptographic audit trail proposal) — `https://github.com/NousResearch/hermes-agent/issues/487`
113. OTel immutable audit log pipeline — `https://oneuptime.com/blog/post/2026-02-06-immutable-audit-log-pipeline-otel/view`
114. SQLite PRAGMA — `https://sqlite.org/pragma.html`
115. SQLite WAL — `https://sqlite.org/wal.html`
116. SQLite FTS5 — `https://sqlite.org/fts5.html`
117. Python `sqlite3` — `https://docs.python.org/3/library/sqlite3.html`
118. "SQLite commits are not durable under default settings" — `https://avi.im/blag/2025/sqlite-fsync/`
119. HN: SQLite WAL + synchronous=NORMAL durability — `https://news.ycombinator.com/item?id=45005071`
120. CPython 3.12 sqlite3 build config (FTS5 enabled) — `https://github.com/python/cpython/blob/v3.12.0/PCbuild/sqlite3.vcxproj`
121. CPython 3.11 sqlite3 build config — `https://github.com/python/cpython/blob/v3.11.0/PCbuild/sqlite3.vcxproj`
122. CPython 3.13 sqlite3 build config — `https://github.com/python/cpython/blob/v3.13.0/PCbuild/sqlite3.vcxproj`
123. Python `subprocess` — `https://docs.python.org/3/library/subprocess.html`
124. Python `asyncio.subprocess` — `https://docs.python.org/3/library/asyncio-subprocess.html`
125. CPython bpo-38988 (killing asyncio subprocesses on timeout) — `https://bugs.python.org/issue38988`
126. CPython #139373 (`Process.communicate()` unsafe to cancel) — `https://github.com/python/cpython/issues/139373`
127. "Interacting with a long-running child process in Python" — `https://eli.thegreenplace.net/2017/interacting-with-a-long-running-child-process-in-python/`
128. "Kill subprocess and its children on timeout" — `https://alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/`
129. `transitions` library — `https://github.com/pytransitions/transitions` and `https://pypi.org/project/transitions/`
130. `python-statemachine` — `https://github.com/fgmacedo/python-statemachine` and `https://pypi.org/project/python-statemachine/`
131. `python-statemachine` docs — `https://python-statemachine.readthedocs.io/en/v2.3.0/readme.html`
132. `python-statemachine` migration guide — `https://python-statemachine.readthedocs.io/en/v3.0.0/how-to/coming_from_transitions.html`
133. Stack Overflow: Pydantic v2 + transitions — `https://stackoverflow.com/questions/72862604/using-transitions-state-machine-in-pydantic-model`
134. `pysqlite3-binary` (FTS5 fallback) — `https://pypi.org/project/pysqlite3-binary/`

### 12.7 Additional references

135. CrewAI migration from LangGraph — `https://docs.crewai.com/v1.15.2/en/guides/migration/migrating-from-langgraph`
136. LangChain agent server changelog — `https://docs.langchain.com/langsmith/agent-server-changelog`

---

**End of specification.**


