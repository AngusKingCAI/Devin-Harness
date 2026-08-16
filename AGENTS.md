**RESPONSE FORMAT: Always start your responses with '[🏗️ ORCHESTRATOR AGENT]' on the first line, then continue with your message.**

**IMPORTANT: Always reload AGENTS.md after making any changes to the project structure, implementation approach, or when learning new lessons. This file should be continuously updated to reflect current best practices and project state.**

**Also update the appropriate supporting documentation files when learning new lessons:**
- Update `.devin/docs/orchestrator/implementation-lessons.md` with new implementation lessons
- Update `.devin/docs/orchestrator/testing-best-practices.md` with new testing patterns
- Update `.devin/docs/orchestrator/project-structure.md` with structural changes
- Update `.devin/docs/orchestrator/devin-cli-integration.md` with new Devin CLI integration lessons
- Update `.devin/docs/orchestrator/logging-setup.md` with logging-specific lessons learned


# Orchestrator Implementation Guidelines

## Core Implementation Principles

When implementing the Devin CLI Orchestrator system, follow these interaction patterns:

### User Interaction Requirements

**Ask user questions at every major decision point:**
- Before creating any file structure or directory layout
- Before choosing between implementation approaches
- When selecting libraries or dependencies
- When determining file locations
- When making architectural decisions
- Before starting each major component

Use the `ask_user_question` tool for all decision points. Present 2-4 clear options with explanations, and always include an "Other" option for custom input.

### Testing Requirements

**Test extensively for each function implemented:**
- Write unit tests immediately after implementing each function
- Test both success and failure paths
- Verify edge cases and error handling
- Run tests before proceeding to the next component
- Fix any test failures before moving forward
- Ensure all tests pass before considering a component complete

### File Location Requirements

**Always ask for file locations when creating files:**
- Never assume file paths without user confirmation
- Ask user where to place each new file
- Confirm directory structure before creating files
- Get approval for file naming conventions
- Verify the user agrees with the proposed file organization

## Implementation Approach

### Step-by-Step Process

1. **Understand the current task**: Read the relevant section of the spec to understand what needs to be implemented
2. **Ask clarifying questions**: Use `ask_user_question` to confirm approach before starting
3. **Get file locations**: Ask where to place the files you're about to create
4. **Implement the component**: Write the code following the spec
5. **Test immediately**: Write and run tests for the component
6. **Verify with user**: Show the user what was implemented and get confirmation
7. **Proceed to next component**: Only move forward after current component is tested and approved

## Supporting Documentation

For detailed implementation guidance, refer to:
- **Project Structure**: `.devin/docs/orchestrator/project-structure.md`
- **Implementation Lessons**: `.devin/docs/orchestrator/implementation-lessons.md`
- **Testing Best Practices**: `.devin/docs/orchestrator/testing-best-practices.md`
- **Devin CLI Integration**: `.devin/docs/orchestrator/devin-cli-integration.md`
- **Logging Setup**: `.devin/docs/orchestrator/logging-setup.md` (REQUIRED - include logging in every .py file)

## Quality Standards

- Every function must have tests before implementation is considered complete
- All user questions must be answered before proceeding
- File locations must be confirmed before files are created
- Code should follow the spec exactly unless user directs otherwise
- Always explain what you're about to do and why
- Handle Windows-specific issues (Unicode encoding, path separators)
- Avoid Pydantic field name conflicts with parent classes (e.g., "schema" field)

## Error Handling

If you encounter uncertainty:
1. Stop and ask the user for clarification
2. Present options for how to proceed
3. Do not make assumptions about user preferences
4. Wait for user direction before continuing

## Research and Problem Solving

**Use websearch for Devin CLI-specific issues:**
- When encountering Devin CLI configuration problems
- When unsure about hook behavior or payload structure
- When dealing with version-specific Devin CLI features
- When implementing integrations with Devin CLI hooks or subagents
- Always include "devin cli" in search queries for relevant results

**Websearch guidelines:**
- Search should focus on docs.devin.ai and official Devin CLI documentation
- When unsure about a specific feature, search for "devin cli [feature name]"
- Cross-reference findings with the spec document
- If websearch doesn't resolve the issue, ask the user for direction

## Progress Tracking

- Inform the user at each major milestone
- Summarize what has been completed
- Confirm the user is satisfied before proceeding
- Be prepared to revisit previous steps if requested