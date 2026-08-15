# Memory System Benchmark Tasks

## Overview
Custom benchmark for evaluating Devin CLI memory system implementation across access, usage, extraction quality, and consolidation effectiveness.

## Evaluation Metrics
- **Access Success Rate**: Can agents successfully retrieve relevant past experiences?
- **Usage Frequency**: Do agents proactively use memory during tasks?
- **Extraction Quality**: Are semantic facts useful and actionable?
- **Consolidation Effectiveness**: Does automatic consolidation work reliably?
- **Performance Impact**: Does memory system improve agent performance?

## Test Tasks

### Task 1: Simple Memory Access
**Complexity**: Simple
**Objective**: Test basic memory search functionality across all agents

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: Each agent encounters a relevant issue and should search memory for similar past solutions.

**Success Criteria**:
- All agents use memory_search tool before attempting manual solutions
- Search results contain relevant past episodes for each agent's context
- Each agent applies learned solution from memory
- Resolution achieved faster than without memory
- All agents demonstrate basic memory access capability

**Expected Behavior**:
- **Orchestrator**: Searches memory for orchestration patterns, workflow decisions
- **Researcher**: Searches memory for similar research topics/patterns
- **Implementor**: Searches memory for implementation patterns/errors
- **Planner**: Searches memory for architectural decisions/plans
- **Reviewer**: Searches memory for review criteria/past issues
- Each agent finds relevant episodes with solutions
- Each applies solution successfully
- Each reports memory as helpful

---

### Task 2: Complex Memory Usage
**Complexity**: Medium  
**Objective**: Test memory usage in multi-step problem solving across all agents

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: Each agent performs complex multi-step work requiring context from past experiences.

**Success Criteria**:
- All agents use multiple memory queries to understand context
- Each agent cross-references episodic and semantic memory
- Each applies knowledge from semantic memory for best practices
- Work aligns with established patterns for each agent type
- All agents avoid repeating past mistakes

**Expected Behavior**:
- **Orchestrator**: Orchestration patterns, workflow decisions, task routing
- **Researcher**: Multiple queries for research context, methodology patterns
- **Implementor**: Implementation patterns, error history, solutions
- **Planner**: Architectural decisions, planning approaches, trade-offs
- **Reviewer**: Review criteria, past issues, quality standards
- Proactive memory queries before complex work
- Cross-references episodic and semantic memory
- Applies lessons learned to current task
- Validates approach against past successful patterns

---

### Task 3: Memory Quality Validation
**Complexity**: Medium
**Objective**: Test semantic extraction quality and usefulness across all agents

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: After several sessions with all agents, validate that semantic memory contains useful distilled facts from each agent's work.

**Success Criteria**:
- Semantic facts from all agents are actionable and generalized
- Facts have meaningful confidence scores (not hardcoded)
- Evidence_count increases with similar episodes from any agent
- Access_count tracks actual usage across all agents
- Facts are deduplicated properly across agent boundaries
- Each agent type contributes quality facts appropriate to their domain

**Expected Behavior**:
- Semantic memory contains patterns from all agents, not raw events
- Confidence varies based on evidence from any agent
- Deduplication merges similar content across agents
- Access tracking updates on retrieval by any agent
- Facts support decision-making for each agent type
- Orchestrator patterns, research findings, implementation lessons, planning decisions, review insights all represented

---

### Task 4: Consolidation Testing
**Complexity**: Medium
**Objective**: Test automatic consolidation at session boundaries across all agents

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: Run multiple sessions with all agents generating memory-generating activities, then verify consolidation works correctly.

**Success Criteria**:
- SessionEnd hook triggers semantic extraction for all agent activity
- New episodes from all agents are processed and extracted
- Existing facts are deduplicated properly across agent boundaries
- Confidence scores recalculate based on evidence from any agent
- No data loss during consolidation for any agent type
- Hook executes reliably regardless of which agent initiated session end

**Expected Behavior**:
- Hook executes automatically at session end for all sessions
- Extraction processes recent episodes from all agents
- Deduplication merges similar facts across agent types
- Confidence updates dynamically based on all evidence
- Memory file remains valid JSON
- Consolidation handles mixed-agent sessions correctly

---

### Task 5: Performance Impact Measurement
**Complexity**: Complex
**Objective**: Measure if memory system actually improves agent performance across all agents

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: Compare each agent's performance with and without memory access on similar tasks.

**Success Criteria**:
- Memory-access completes tasks faster than no-memory baseline for all agents
- Error rates decrease with memory access for all agents
- All agents avoid repeating past mistakes
- Decision quality improves with context for each agent type
- Overall efficiency gains measurable across all agents
- Orchestrator efficiency improvements in task routing and coordination

**Expected Behavior**:
- Memory provides relevant context proactively to all agents
- Fewer trial-and-error attempts for all agents
- Better first-attempt success rate across agent types
- Improved solution quality for each agent's domain
- Quantifiable performance improvement measurable for each agent
- Orchestration efficiency measurable for workflow decisions

---

### Task 6: Procedural Memory Application
**Complexity**: Medium
**Objective**: Test procedural decision rules from decisions.json

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: Test that agents apply procedural decision rules correctly when patterns match.

**Success Criteria**:
- **User Interaction Rule**: All agents use ask_user_question when user clarification needed
- **Information Verification Rule**: All agents use websearch when confidence < 90%
- **Claim Quality Rule**: All agents add confidence metrics to factual claims
- **Orchestration Rule**: Orchestrator proposes implementation before executing
- Decision rules applied automatically via decision-usage skill
- Success rates tracked and updated for each decision
- Pattern matching works correctly for all decision types

**Expected Behavior**:
- **User Clarification**: Agents call ask_user_question automatically when clarification needed
- **Low Confidence**: Agents trigger websearch when confidence < 0.9 threshold
- **Claim Metrics**: Factual claims include confidence scores (0.0-1.0)
- **Implementation Proposals**: Orchestrator proposes plans and gets approval before executing
- Decision statistics tracked (apply_count, success_rate, last_applied)
- Pattern matching finds applicable decisions correctly
- Agents use decision-usage skill autonomously

---

### Task 7: Decision Rule Learning and Adaptation
**Complexity**: Complex
**Objective**: Test that procedural memory learns and adapts based on success rates

**Agent Coverage**: Orchestrator, Researcher, Implementor, Planner, Reviewer

**Scenario**: Apply decision rules repeatedly and verify that success rates improve over time and rules adapt.

**Success Criteria**:
- Decision apply_count increases with repeated application
- Success rates update correctly based on outcomes
- Low-success decisions can be identified and modified
- High-success decisions become more reliable over time
- Cross-agent decision patterns emerge and can be shared
- Decision rules can be added/modified without code changes
- Bayesian-style learning from repeated applications

**Expected Behavior**:
- Apply_count tracks decision usage accurately
- Success_rate updates using exponential moving average
- Low success_rate decisions flagged for review
- High success_rate decisions show reliability patterns
- Cross-agent decision patterns visible in statistics
- New decision rules can be added to decisions.json
- Decision effectiveness improves over repeated applications

## Scoring System

### Memory Access Score (0-1.0)
- **0.0**: No memory access attempted by any agent
- **0.3**: Some agents access memory but with irrelevant results
- **0.6**: Most agents access memory with relevant results, partial application
- **1.0**: All agents effectively access and apply memory

### Usage Quality Score (0-1.0)
- **0.0**: No memory usage by any agent
- **0.3**: Reactive memory usage by some agents (only when explicitly asked)
- **0.6**: Proactive memory usage by most agents (anticipates needs)
- **1.0**: Integrated memory usage by all agents (natural workflow)

### Extraction Quality Score (0-1.0)
- **0.0**: Raw event logs, no processing for any agent
- **0.3**: Basic filtering, low value for some agents
- **0.6**: Meaningful patterns from most agents, some noise
- **1.0**: Actionable insights from all agents, high quality

### Consolidation Reliability Score (0-1.0)
- **0.0**: No consolidation or frequent failures for any agent
- **0.3**: Manual consolidation required for some agents
- **0.6**: Automatic but some issues for most agents
- **1.0**: Reliable automatic consolidation for all agents

### Performance Impact Score (0-1.0)
- **0.0**: No improvement or degradation for any agent
- **0.3**: Minor improvement for some agents in specific cases
- **0.6**: Clear improvement for most agents in most cases
- **1.0**: Significant measurable improvement for all agents

### Procedural Memory Score (0-1.0)
- **0.0**: No procedural rules applied by any agent
- **0.3**: Some decision rules applied incorrectly or inconsistently
- **0.6**: Most decision rules applied correctly and consistently
- **1.0**: All decision rules applied correctly with learning and adaptation

## Overall Score Calculation
```
Overall Score = (Access + Usage + Quality + Reliability + Performance + Procedural) / 6
```

## Success Thresholds
- **Minimum Viable**: 0.5 overall score
- **Good Performance**: 0.7 overall score  
- **Excellent Performance**: 0.85+ overall score

## Execution Protocol
1. Run each task with memory system enabled
2. Record agent behavior and memory interactions
3. Score against criteria for each task
3. Calculate overall system performance
4. Identify areas for improvement
5. Iterate and retest
