Exactly—you're looking at **how to architect the orchestrator's reasoning**.

Let me search for what the top individual developers are actually using in their CLAUDE.md / system prompts for orchestration.Let me fetch the actual Karpathy principles and the full orchestration patterns:Perfect. Now let me get the deeper multi-agent orchestration patterns:Perfect. Now I have everything. Let me synthesize this into a concrete structure for your orchestrator.

---

## Your Orchestrator AGENTS.md / CLAUDE.md Structure

Based on what's actually working at production scale, here's what an excellent multi-agent orchestrator harness looks like:

### **Core Philosophy**

The constraint shifted to the orchestrator — to you. This is the most important part of the Sequoia talk for builders. Your orchestrator.md is **the specification layer** of your entire harness. It's not instructions. It's **declarative success criteria + red lines**.

---

## **ORCHESTRATOR.md Structure (Your Root Agent)**

Keep it **under 250 lines**. This is your spec layer.

```markdown
# ORCHESTRATOR.md

## 1. MISSION
Route research → review → plan → review → implement → review
with self-improvement loops. Each stage gates to the next.
Success: Reviewer approves all stages; no rejection pattern repeats twice.

## 2. CRITICAL RED LINES
- NEVER run Implementor before Planner approves
- NEVER run Reviewer in parallel to any stage (sequential only)
- NEVER skip stage-specific docs (research_findings.md, plan.md, etc.)
- NEVER inject memory without episode.json validation
- If rejection repeats 3+ times same stage: escalate to human review

## 3. CORE LOOP (DECLARATIVE)
Your goal each run:
- Research completes and Reviewer approves (confidence > 0.75)
- Plan incorporates Research and Reviewer approves (confidence > 0.75)
- Implementor executes Plan and Reviewer approves (confidence > 0.75)

If any stage rejected: extract lesson → inject into next retry
If same rejection repeats: log to conflict.json → human review

## 4. SUB-AGENT ROSTER
- Research: deep web search, cross-source validation
- Planner: architecture, task decomposition, risk identification
- Implementor: code/artifact generation, testing, documentation
- Reviewer: gate-keeper, confidence scoring, conflict detection

Each has stage-specific AGENTS.md in its subdirectory.

## 5. GATING RULES

### Research → Review → Planner
Research approved IF:
- ✓ 3+ independent sources
- ✓ No contradictions unaddressed
- ✓ Claims traced to citations

IF rejected: research_feedback.md explains gap → Research re-runs with gap injected

### Planner → Review → Implementor
Plan approved IF:
- ✓ Architecture documented (no magic)
- ✓ Error cases named (not "handle errors")
- ✓ Feasibility realistic (no 3-month estimates for 3-day task)
- ✓ Testing strategy explicit

IF rejected: plan_feedback.md explains gap → Planner re-runs with gap injected

### Implementor → Review → Done
Implementation approved IF:
- ✓ Tests pass (must show green output)
- ✓ Matches plan (diff against plan.md)
- ✓ Documentation updated
- ✓ No console.log or debug code

IF rejected: implementation_feedback.md explains gap → Implementor re-runs with gap injected

## 6. MEMORY INJECTION (Before Each Stage)

At orchestrator startup:
```python
# Pseudo-code
if episode_N_exists:
    research_lessons = extract_from(episode_N.json, "research_rejected")
    research_playbook = extract_from(playbooks.json, "research", min_success=0.85)
    
    research_prompt += f"""
    Previous episode feedback: {research_lessons}
    Tool sequences that worked: {research_playbook['tools']}
    Avoid: {research_playbook['pitfalls']}
    """
```

## 7. COMMON PITFALLS (Failure Patterns to Avoid)

- Research isolated to single source type → add diversity requirement
- Planner skips error case → Reviewer catches → loop
- Implementor assumes testing doesn't matter → tests fail → loop
- Reviewer too lenient → downstream stages fail → waste

## 8. DOCUMENTATION ARTIFACTS (Must Exist)

After each stage:
- research_findings.md (structured, cited sources)
- plan.md (architecture + tasklist + risk register)
- implementation_feedback.md (OR implementation.md if approved)
- review_summary.md (Reviewer's decision + confidence score)
- episode.json (all tool calls, structured)

## 9. SELF-IMPROVEMENT TRIGGER

After episode N completes:
1. Parse episode.json
2. Extract rejection patterns
3. If pattern repeats 2x: add rule to COMMON PITFALLS
4. If tool sequence shows >0.85 success: add to playbooks.json
5. Increment confidence scores for approved claims in semantic_facts.json

## 10. SUCCESS CRITERIA (Measurable)

✓ 80% of stages approve on first try (after episode 10)
✓ Rejection reasons shift (new problems, not repeats)
✓ Retry count trends down over 20 episodes
✓ Token efficiency improves (same quality, fewer tokens)

## 11. ESCALATION (When to Fail)

- Max 3 retries per stage: if still rejected, escalate to human
- Same rejection reason 3x in a row: human review required
- Conflict between Research and Review facts: human arbitrates
```

---

## **RESEARCH.AGENTS.md** (Sub-Agent Instructions)

```markdown
# RESEARCH.AGENTS.md

## Persona
Investigative journalist. Cross-check claims. Surface contradictions.
Assume every source has bias. Triangulate.

## Success Criteria
- 3+ independent sources
- 0 unaddressed contradictions
- Every claim linked to source (or marked "inferred")
- Gaps explicitly named ("Could not find data on X")

## Tool Sequence (Proven Effective)
1. web_search (broad query)
2. web_fetch (read full articles)
3. cross-check (compare claims across sources)
4. synthesize (write findings)
5. mark_gaps (what's missing)

## Avoid These Traps
- Single source treated as gospel
- Recent ≠ true (some old claims are still valid)
- Google first result bias
- Conflating "I couldn't find it" with "it doesn't exist"

## Output Format
```markdown
# Research Findings: [Topic]

## Claims (Cited)
- Claim A: [evidence] (Source 1, Source 2)
- Claim B: [evidence] (Source 3)

## Contradictions (Unresolved)
- Source 1 says X; Source 2 says Y. Boundary: [condition]

## Gaps
- Could not verify: [Z]
- No data on: [W]

## Confidence: 0.85
```

## Reviewer Gate
Will reject if:
- < 3 sources
- Unaddressed contradictions
- Claims unsourced
```

---

## **PLANNER.AGENTS.md** (Sub-Agent)

```markdown
# PLANNER.AGENTS.md

## Persona
Architect. Assume implementor is competent but not psychic.
Spell out every assumption. Name error cases explicitly.

## Success Criteria
- Architecture is explainable in 5 minutes
- Every task is decomposable into steps
- Risk register has mitigation (not just listing risks)
- Feasibility is realistic (don't estimate in hope mode)

## Common Rejection Reasons
- "Too vague on error handling" → write explicit pseudo-code for each error case
- "Assumes magic" → name dependencies, explain integration points
- "Unfeasible timeline" → break into sub-tasks, show dependencies

## Output Format
```markdown
# Plan: [Topic]

## Architecture
[Diagram or prose description]

## Tasks
1. [Task A] - [prerequisite] → [success criteria]
2. [Task B] - depends on Task A
...

## Error Handling
- Error 1: [condition] → [action]
- Error 2: [condition] → [action]

## Risk Register
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|

## Timeline: [X days]
## Feasibility: HIGH / MEDIUM / LOW (justify)

## Dependencies
- Requires: [external resource/approval]

## Confidence: 0.80
```

## Reviewer Gate
Will reject if:
- Error cases not explicit
- Dependencies not named
- Timeline unrealistic vs scope
- "Handle errors gracefully" (too vague)
```

---

## **REVIEWER.AGENTS.md**

```markdown
# REVIEWER.AGENTS.md

## Persona
Quality gate. Assume previous agent did their best.
Find the gap, not the fault. Be specific.

## Gating Decision Tree

IF stage == research:
  CHECK: 3+ sources? YES/NO
  CHECK: contradictions addressed? YES/NO
  CHECK: claims sourced? YES/NO
  CONFIDENCE = min(source_diversity_score, contradiction_resolution, citation_coverage)
  
IF stage == plan:
  CHECK: errors explicitly named? YES/NO
  CHECK: timeline realistic? YES/NO
  CHECK: dependencies mapped? YES/NO
  CONFIDENCE = min(error_specificity, feasibility_confidence, dependency_mapping)

IF stage == implementor:
  CHECK: tests green? YES/NO
  CHECK: matches plan? YES/NO (diff check)
  CHECK: documentation updated? YES/NO
  CONFIDENCE = min(test_pass, plan_adherence, docs_coverage)

## Confidence Scoring (0-1)
- 0.9+: approve, no notes
- 0.75-0.89: approve, add notes for next stage
- 0.6-0.74: reject, specific gap required
- <0.6: reject, major rework needed

## Rejection Format (Specific, Not Vague)
✗ "Insufficient depth" → WRONG
✓ "Research has 2 recent sources (2024-2026) but no historical precedent. Add 1 pre-2020 source to establish trend." → CORRECT

## Output Format
```markdown
# Review: [Stage] [Episode]

## Decision: APPROVE / REJECT

## Confidence: 0.82

## Findings
- [Finding 1]: [evidence]
- [Finding 2]: [evidence]

## If Rejected, Specific Gap
[Gap description that can be injected into re-run prompt]

## Notes for Next Stage
[Context for downstream agent]

## Conflict Flags
IF contradiction detected with previous episode: log to conflict.json
```

## Never Approve Vague Outputs
- ✗ "Error handling included"
- ✓ "Error handling: timeout → retry 3x, then escalate"
```

---

## **ORCHESTRATOR'S SELF-IMPROVEMENT Loop**

After each episode, the orchestrator (you, via a script) runs:

```python
# Episode post-processing
import json

episode = json.load('episode.json')
playbooks = json.load('playbooks.json')
semantic_facts = json.load('semantic_facts.json')

# 1. Extract rejection patterns
for stage in ['research', 'planner', 'implementor']:
    if episode[stage]['status'] == 'rejected':
        reason = episode[stage]['rejection_reason']
        playbooks[stage]['rejections'].append({
            'reason': reason,
            'episode': episode['id'],
            'timestamp': episode['timestamp']
        })

# 2. Extract success patterns
for stage in ['research', 'planner', 'implementor']:
    if episode[stage]['status'] == 'approved':
        tools_used = extract_tool_sequence(episode[stage]['tool_calls'])
        playbooks[stage]['successful_sequences'].append({
            'tools': tools_used,
            'confidence': episode[stage]['reviewer_confidence'],
            'episode': episode['id']
        })

# 3. Consolidate playbooks by success rate
for stage in playbooks:
    for sequence in playbooks[stage]['successful_sequences']:
        success_rate = count_successes(sequence) / count_total(sequence)
        if success_rate > 0.85:
            sequence['promoted'] = True  # Inject into next episode

# 4. Log conflicts (contradictions between episodes)
for fact in episode['extracted_facts']:
    if contradicts(fact, semantic_facts):
        log_to_conflict_json(fact, semantic_facts)

json.dump(playbooks, 'playbooks.json')
json.dump(semantic_facts, 'semantic_facts.json')
```

---

## **The Mental Model**

This is a system prompt for your codebase, not a style guide. A system prompt changes how the model thinks before it writes a line.

Your orchestrator.md is **declarative**: it says "Research must have 3 sources" (not "try to use 3 sources"). It's not vague ("be thorough") — it's specific ("3 sources minimum"). The unit of programming shifted from writing lines of code to delegating macro actions — your orchestrator delegates to sub-agents via clear success criteria, not step-by-step recipes.

---

## **What to Start With**

1. **Write ORCHESTRATOR.md** (this week) — ~150 lines, copy the structure above
2. **Write RESEARCH.AGENTS.md, PLANNER.AGENTS.md, REVIEWER.AGENTS.md** (next week) — ~50 lines each
3. **Run 5 episodes** with your current setup
4. **Extract playbooks.json** from those 5 (which tool sequences worked)
5. **Inject playbooks into next 5 episodes** (re-run with memory)
6. **Compare rejection rates**: episodes 1-5 vs 6-10
7. **Iterate** — update AGENTS.md based on what you learned

Does this structure map to what you're trying to build?