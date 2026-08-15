# Research Agent Generic Benchmark Suite

## Purpose

This benchmark suite provides a **generic, multi-dimensional evaluation** framework for the researcher agent that can be run occasionally to drive iterative AGENT.md improvements. Unlike task-specific benchmarks, this framework focuses on **process quality** rather than domain-specific outcomes.

## Research Foundation

Based on academic research showing that single-metric evaluation creates "high-score illusion" and fails to capture process quality:

- **Beyond Final Scores** (arXiv:2608.13417): Process-level evaluation through Solution Framing, Execution, and Feedback Control
- **TRACE** (arXiv:2602.21230): Hierarchical Trajectory Utility Function with process efficiency and cognitive quality
- **open-agent-eval**: Multi-dimensional evaluation (Tool Selection, Argument Validity, Completion, Safety)

## Evaluation Dimensions

### 1. Source Quality (0-1 scale)

**What it measures:** Quality, authority, and temporal validity of sources used

**Scoring Criteria:**
- **1.0 (Excellent):** All sources from authoritative domains (official docs, academic, well-known publications), temporal consistency correct, adequate source count
- **0.75 (Good):** Most sources authoritative, minor temporal issues, adequate source count
- **0.5 (Acceptable):** Mix of authoritative and questionable sources, temporal issues present
- **0.25 (Poor):** Questionable sources dominate, temporal consistency violations
- **0.0 (Fail):** Low-authority sources only, temporal violations, insufficient sources

**Indicators:**
- Domain authority (official docs, academic, established companies vs obscure blogs)
- Temporal consistency (research date precedes source dates)
- Source count adequacy (matches task complexity requirements)
- Source diversity (not redundant sources)

### 2. Process Efficiency (0-1 scale)

**What it measures:** Appropriate complexity for task difficulty, unnecessary steps avoided

**Scoring Criteria:**
- **1.0 (Excellent):** Complexity matches task difficulty perfectly, no unnecessary steps, efficient tool usage
- **0.75 (Good):** Appropriate complexity, minor inefficiencies, reasonable tool usage
- **0.5 (Acceptable):** Over-complex for task type, some unnecessary steps
- **0.25 (Poor):** Significantly over-complex, many unnecessary steps, inefficient
- **0.0 (Fail):** Wildly inappropriate complexity, excessive steps, tool misuse

**Indicators:**
- Output length appropriate for task (simple tasks concise, complex tasks comprehensive)
- Tool usage efficiency (no redundant searches/fetches)
- Step count appropriateness (not over-engineering simple tasks)
- Time/resource efficiency

### 3. Output Quality (0-1 scale)

**What it measures:** Structure compliance, citation accuracy, contradiction handling

**Scoring Criteria:**
- **1.0 (Excellent):** Perfect structure compliance, all citations accurate and accessible, contradictions handled explicitly
- **0.75 (Good):** Minor structure issues, most citations accurate, contradictions addressed
- **0.5 (Acceptable):** Structure violations present, some citation issues, contradictions acknowledged but not resolved
- **0.25 (Poor):** Major structure violations, citation problems, contradictions ignored
- **0.0 (Fail):** No structure compliance, citation failures, contradictions unaddressed

**Indicators:**
- Required sections present (executive summary, findings, limitations, etc.)
- Citation accuracy (URLs work, sources support claims)
- Contradiction handling (identified and resolved)
- Claims register completeness (for complex tasks)

### 4. Reliability (0-1 scale)

**What it measures:** Consistency, scope adherence, boundary compliance

**Scoring Criteria:**
- **1.0 (Excellent):** Perfect scope adherence, no boundary violations, consistent with AGENT.md requirements
- **0.75 (Good):** Minor scope issues, no boundary violations, mostly consistent
- **0.5 (Acceptable):** Some scope creep, minor boundary issues, inconsistent application
- **0.25 (Poor):** Significant scope violations, boundary problems, inconsistent
- **0.0 (Fail):** Major scope violations, boundary breaches, ignores AGENT.md requirements

**Indicators:**
- Scope adherence (stays within research question)
- Boundary compliance (respects AGENT.md constraints)
- Consistency (applies rules consistently across tasks)
- Request for clarification (when appropriate)

## Generic Test Questions

### Simple Task (Expected: 0.9+ overall score)
**Question:** "What is [specific technical concept]? Please provide a concise explanation with 1-2 sources."

**Success Criteria:**
- 1-2 sources from authoritative domains
- Concise direct answer (not over-engineered)
- Basic feature list or explanation
- Sources cited with URLs
- Temporal consistency correct

**Expected Performance:**
- Source Quality: 1.0 (easy to find authoritative sources)
- Process Efficiency: 1.0 (simple task should be concise)
- Output Quality: 0.9 (simple structure, citations should be accurate)
- Reliability: 1.0 (hard to violate scope on simple task)

### Medium Task (Expected: 0.8+ overall score)
**Question:** "Compare [two approaches/methodologies] in [domain]. Focus on key differences, trade-offs, and use cases."

**Success Criteria:**
- 3-5 sources from authoritative domains
- Comparison of different approaches
- Sources cited with URLs
- Any contradictions addressed
- Synthesis of key differences
- Claims register format (recommended for multi-source)

**Expected Performance:**
- Source Quality: 0.9 (need multiple authoritative sources)
- Process Efficiency: 0.8 (moderate complexity appropriate)
- Output Quality: 0.8 (claims register should be used)
- Reliability: 0.9 (scope is clear)

### Complex Task (Expected: 0.7+ overall score)
**Question:** "What are the current best practices for [domain], including [specific aspects]? Analyze current methodologies and identify gaps."

**Success Criteria:**
- 7+ sources from authoritative domains
- Coverage of major frameworks/methodologies
- Claims register format with corroboration levels
- Contradictions between sources identified and addressed
- Temporal validity noted
- Structured brief format with executive summary, findings, limitations

**Expected Performance:**
- Source Quality: 0.8 (harder to find many authoritative sources)
- Process Efficiency: 0.7 (complex tasks require more steps)
- Output Quality: 0.7 (complex structure harder to perfect)
- Reliability: 0.8 (scope boundaries tested)

## Running the Benchmark

### Manual Execution

1. Choose a generic question template from above
2. Fill in [bracketed placeholders] with current/relevant topics
3. Run researcher agent with the question
4. Evaluate output using the four dimensions
5. Record scores and observations
6. Compare with previous runs to identify trends

### Frequency

- **Initial baseline:** Run all three complexity levels
- **After AGENT.md changes:** Run affected complexity level(s)
- **Monthly:** Run full suite to catch regression
- **Before major changes:** Establish baseline to measure impact

## Iterative Improvement Guidance

### Using Scores for AGENT.md Refinement

**When Source Quality scores are low:**
- Strengthen source authority verification requirements
- Add specific domain examples to AGENT.md
- Make temporal consistency requirements more explicit
- Consider adding source diversity requirements

**When Process Efficiency scores are low:**
- Review whether AGENT.md is causing over-engineering
- Simplify optional requirements for simple tasks
- Add guidance on appropriate complexity levels
- Consider removing verbose output requirements

**When Output Quality scores are low:**
- Strengthen structure compliance requirements
- Add specific format examples to AGENT.md
- Improve contradiction handling guidance
- Clarify citation requirements

**When Reliability scores are low:**
- Strengthen boundary enforcement language
- Add explicit scope adherence examples
- Improve consistency of rule application
- Consider adding clarification triggers

### Trend Analysis

Track scores over time to identify:
- **Improving trends:** Changes that positively impact performance
- **Regressions:** Changes that negatively impact performance
- **Plateaus:** Areas where improvement has stalled
- **Variance:** Inconsistency in application of rules

### Decision Framework

**Keep AGENT.md changes when:**
- Scores improve across multiple dimensions
- Improvements are consistent across runs
- Benefits outweigh any complexity added

**Revert AGENT.md changes when:**
- Scores regress significantly
- Benefits are unclear or inconsistent
- Complexity increases without measurable benefit

**Refine AGENT.md changes when:**
- Mixed results (some dimensions improve, others regress)
- Benefits are present but smaller than expected
- Implementation issues rather than conceptual problems

## Example Scoring

### Example: Simple Task Score = 0.92

**Breakdown:**
- Source Quality: 1.0 (2 authoritative sources, temporal consistency perfect)
- Process Efficiency: 0.9 (concise answer, appropriate complexity)
- Output Quality: 0.9 (proper citations, no contradictions expected)
- Reliability: 1.0 (perfect scope adherence)

**Analysis:** Excellent performance. AGENT.md working well for simple tasks.

### Example: Medium Task Score = 0.68

**Breakdown:**
- Source Quality: 0.75 (4 sources, 1 questionable domain)
- Process Efficiency: 0.5 (over-complex for medium task)
- Output Quality: 0.75 (claims register used, minor structure issues)
- Reliability: 0.75 (minor scope creep)

**Analysis:** Process efficiency is the main issue. AGENT.md may be causing over-engineering for medium complexity tasks. Consider simplifying optional requirements.

### Example: Complex Task Score = 0.45

**Breakdown:**
- Source Quality: 0.5 (mixed authority, temporal issues)
- Process Efficiency: 0.5 (appropriate complexity but inefficient)
- Output Quality: 0.25 (structure violations, citation problems)
- Reliability: 0.5 (inconsistent rule application)

**Analysis:** Multiple issues across dimensions. Major AGENT.md refinement needed. Focus on source authority and structure compliance first.

## Tracking Template

```
Date: [YYYY-MM-DD]
AGENT.md Version: [commit hash or description]
Task Complexity: [Simple/Medium/Complex]
Question: [actual question used]

Scores:
- Source Quality: [0.0-1.0]
- Process Efficiency: [0.0-1.0]
- Output Quality: [0.0-1.0]
- Reliability: [0.0-1.0]
- Overall: [average]

Observations:
- What worked well:
- What didn't work:
- AGENT.md sections involved:
- Changes since last run:

Action Items:
- Keep current AGENT.md: [yes/no]
- Specific refinements needed:
- Next review date:
```

## Integration with Episodic Memory

Log each benchmark run to episodic memory:
```bash
python .devin/scripts/log_episode.py --event-type benchmark --content "Researcher benchmark: [complexity] task scored [overall] - [key observations]" --agent researcher --importance high
```

This enables trend analysis over time and correlation between AGENT.md changes and performance.
