---
triggers: ["user", "model"]
description: Check and apply procedural decision rules for consistent behavior
subagent: true
---

# Decision Usage Skill

## Purpose
Check and apply procedural decision rules from decisions.json to ensure consistent behavior across all agents.

## When to Use
- When you need to ask the user a question
- When providing information or making claims
- When making factual claims with confidence levels
- When consistent decision patterns should be applied

## Decision Rules Available

### User Interaction Rules
- **Default Rule**: Use ask_user_question when user clarification needed
- **Confidence Threshold**: Automatic enforcement
- **Pattern**: "When user clarification needed"

### Information Verification Rules  
- **Websearch Rule**: Use websearch if not 90%+ confident on answers
- **Confidence Threshold**: 0.9
- **Pattern**: "When providing information or making claims"

### Claim Quality Rules
- **Confidence Metrics**: Add confidence scores (0.0-1.0) to claims
- **Confidence Threshold**: 0.8
- **Pattern**: "When making factual claims"

### Orchestration Rules
- **Propose Implementation**: When asked a question, propose implementation rather than automatically doing it
- **Confidence Threshold**: 0.8
- **Pattern**: "When user asks for implementation or action"

## Procedure

1. **Check Applicable Decisions**: Use decision_check MCP tool
   ```
   Call: mcp__memory__decision_check(pattern="<your current action>")
   ```

2. **Apply Decision Rules**: Follow returned decision actions
   ```
   Call: mcp__memory__decision_apply(decision_id="<decision_id>")
   ```

3. **Track Success**: Update decision statistics
   ```
   Call: mcp__memory__decision_update_stats(decision_id="<decision_id>", success=<true/false>)
   ```

4. **Get Confidence Thresholds**: Use for claim verification
   ```
   Call: mcp__memory__decision_get_confidence_threshold(claim_type="<type>")
   ```

## Examples

**User Question Scenario:**
```
Pattern: "user clarification needed"
Decision: Use ask_user_question tool
Apply: Call ask_user_question with your question
Track: Update stats with success status
```

**Information Verification:**
```
Pattern: "providing information"  
Decision: Check confidence level
If confidence < 0.9: Use websearch for verification
If confidence >= 0.9: Provide information directly
Track: Update stats based on result
```

**Claim with Confidence:**
```
Pattern: "making factual claims"
Decision: Include confidence score
Format: "X is true (confidence: 0.85)"
Apply: Add confidence to all factual claims
Track: Update based on claim accuracy
```

**Implementation Proposal:**
```
Pattern: "user asks for implementation"
Decision: Propose implementation plan
Format: "I propose to [X] by [Y]. Should I proceed?"
Apply: Get user approval before executing
Track: Update based on user satisfaction
```

## Benefits

- **Consistency**: All agents follow the same decision patterns
- **Quality**: Confidence thresholds ensure high-quality outputs
- **Learning**: Success rates track which decisions work best
- **Transparency**: Confidence metrics make uncertainty explicit
