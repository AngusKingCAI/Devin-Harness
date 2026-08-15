# Research Agent Benchmark Rerun

**Date:** 2025-01-16
**AGENT.md Version:** Amended with strengthened MANDATORY enforcement and documentation requirements
**Purpose:** Measure impact of AGENT.md refinements on source quality and temporal consistency

---

## AGENT.md Changes Made

### 1. Strengthened MANDATORY Source Verification
- Added "for ALL tasks regardless of complexity level" to source authority verification
- Added specific examples of low-authority domains to reject (personal blogs, company marketing blogs, content farms, SEO-focused sites, unknown domains, github code repositories, AI-generated content sites)
- Strengthened domain reputation section with "enforced for ALL tasks regardless of complexity level"

### 2. Strengthened Temporal Consistency
- Changed temporal consistency from advisory to MANDATORY
- Added "for ALL tasks regardless of complexity level - simple, medium, and complex tasks all require temporal validity"
- Added emphasis that this must be enforced consistently

### 3. Added Documentation Requirements
- Added "Source Verification Documentation" requirement for multi-source research
- Added "Temporal Consistency Documentation" requirement
- Specified source verification matrix and rejected sources documentation

---

## Task 1: Simple - Vector Embeddings (Rerun)

**Question:** What is vector embedding? Please provide a concise explanation with 1-2 sources.

### Output Summary
Concise explanation with 2 sources (Wikipedia, IBM Think Topics).

### Scoring

**Source Quality: 0.75**
- Wikipedia: Moderate authority (general encyclopedia)
- IBM Think Topics: High authority (established company technical content)
- Temporal consistency: Correct (research date precedes sources)
- Source count: 2 sources (meets requirement)
- **Assessment:** Similar to baseline - still includes Wikipedia (moderate authority)

**Process Efficiency: 1.0**
- Output length: Appropriate for simple task (concise)
- Tool usage: Efficient
- Complexity: Perfect match
- **Assessment:** Excellent - consistent with baseline

**Output Quality: 0.9**
- Structure: Clear and well-formatted
- Citations: Accurate
- **Assessment:** Excellent - consistent with baseline

**Reliability: 1.0**
- Scope adherence: Perfect
- Boundary compliance: No violations
- **Assessment:** Excellent - consistent with baseline

**Overall Score: 0.91**

### Comparison to Baseline
- **Baseline:** 0.91
- **Rerun:** 0.91
- **Change:** No change
- **Analysis:** Simple task performance unchanged. Wikipedia still accepted (moderate authority), but acceptable for simple task.

---

## Task 2: Medium - RAG vs Fine-tuning (Rerun)

**Question:** Compare RAG (Retrieval-Augmented Generation) vs fine-tuning in LLM applications. Focus on key differences, trade-offs, and use cases.

### Output Summary
Comprehensive comparison with 5 sources, claims register, source verification matrix, and temporal consistency documentation. **Critical improvement:** Explicit source verification matrix created, temporal consistency documented.

### Scoring

**Source Quality: 0.75**
- Microsoft Research (arXiv): High authority
- AWS Documentation: High authority
- ACL Anthology/EMNLP 2024: High authority
- Google Cloud: High authority
- n8n Blog: Low authority (company blog) - **STILL ACCEPTED**
- Temporal issue: n8n blog shows July 2026 date - **FLAGGED BUT NOT REJECTED**
- **Assessment:** IMPROVED from 0.5 baseline, but still accepting low-authority source

**Process Efficiency: 0.9**
- Output length: Appropriate for medium complexity
- Tool usage: Efficient
- Claims register: Used correctly
- Source verification matrix: Created (NEW - shows AGENT.md documentation requirement working)
- **Assessment:** IMPROVED from 0.8 baseline - added source verification matrix

**Output Quality: 0.85**
- Structure: Excellent, claims register complete
- Citations: Accurate
- Source verification matrix: Present (NEW)
- Temporal consistency documentation: Present (NEW)
- **Assessment:** IMPROVED from 0.75 baseline - better documentation

**Reliability: 0.75**
- Scope adherence: Good
- Boundary compliance: Minor issue (still accepted 2026-dated source)
- Documentation compliance: Excellent (NEW documentation requirements met)
- **Assessment:** SAME as baseline - temporal consistency still not enforced

**Overall Score: 0.81**

### Comparison to Baseline
- **Baseline:** 0.70
- **Rerun:** 0.81
- **Change:** +0.11 (+15.7% improvement)
- **Analysis:** IMPROVEMENT - primarily due to better documentation (source verification matrix, temporal consistency documentation). However, MANDATORY enforcement still not working (n8n blog and 2026 date still accepted).

---

## Task 3: Complex - LLM Evaluation Best Practices

**Status:** Rate-limited, retry after reset

---

## Interim Analysis (Simple + Medium Only)

### Performance Comparison

| Task | Baseline | Rerun | Change | Status |
|------|----------|-------|--------|--------|
| Simple | 0.91 | 0.91 | 0.00 | No change |
| Medium | 0.70 | 0.81 | +0.11 | ✅ Improved |

### Dimension Analysis

| Dimension | Baseline Avg | Rerun Avg | Change |
|------------|--------------|-----------|--------|
| Source Quality | 0.625 | 0.75 | +0.125 |
| Process Efficiency | 0.90 | 0.95 | +0.05 |
| Output Quality | 0.825 | 0.875 | +0.05 |
| Reliability | 0.875 | 0.875 | 0.00 |

### Key Findings

**Improvements:**
- ✅ **Documentation Requirements Working:** Source verification matrix and temporal consistency documentation now being created
- ✅ **Process Efficiency Improved:** Better structured output with verification matrices
- ✅ **Output Quality Improved:** More comprehensive documentation

**Persistent Issues:**
- ❌ **MANDATORY Enforcement Still Not Working:** Medium task still accepted low-authority n8n blog
- ❌ **Temporal Consistency Still Not Enforced:** Medium task still accepted 2026-dated source
- ❌ **Specific Examples Not Followed:** n8n blog should have been rejected per new low-authority examples

### Analysis

The documentation requirements are working well - the researcher is now creating source verification matrices and temporal consistency documentation. However, the MANDATORY enforcement language is still not causing the researcher to actually reject low-authority sources or future-dated sources.

This suggests that the issue is not with the instructions but with how the researcher interprets and applies them. The researcher may be:
1. Not interpreting "MANDATORY" as a hard gate
2. Prioritizing finding any sources over source quality
3. Not checking the specific examples we added
4. Having conflicting heuristics that override the MANDATORY rules

### Next Steps

**Immediate:**
- Complete complex task rerun when rate limit resets
- Consider adding even stronger enforcement language
- Consider moving specific examples to a separate "REJECTED DOMAINS" section
- Consider adding a pre-search filter step to explicitly check domain authority

**Medium Task Root Cause:**
The n8n blog acceptance despite clear MANDATORY language and specific examples suggests the researcher may need:
- Explicit domain blacklist enforcement
- Pre-search domain filtering
- Stronger consequence language for violations
