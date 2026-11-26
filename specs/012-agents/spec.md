# Feature Specification: Agents

**Feature Branch**: `012-agents`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "issue 012" — feature 012 from the team plan (`docs/product/team-workflow.md`,
round 4, issue #28): "Agents: Explorer, Analyst and Reviewer in a LangGraph state graph on top of the 011
verifier and agent tools. Shared state holds the question, evidence, claims and a step budget (about 15 tool
calls, at most 2 revisions); Reviewer checks every claim with plain code, sends weak claims back to Explorer
and downgrades them to hypotheses when the budget runs out. The final answer is phrased only from verified
claims, with citations; the model is set by one config line (Ollama by default). Depends on 011."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An architecture question gets an answer whose facts are all proven (Priority: P1)

A developer has an analyzed snapshot of a repository and asks "What breaks if I change `auth/service.py`?".
The agents explore the snapshot with the read-only tools of feature 011: the Explorer finds the file and the
symbols in it, the Analyst asks for its dependents and impact and turns the results into claims with
citations, and the Reviewer checks every claim with the 011 verifier, which is plain code. The developer gets
an answer in which every statement given as a fact comes from a verified claim and carries its citation
`path:line@snapshot`; likely links are said to be likely, and nothing unproven is stated as a fact.

**Why this priority**: This is the product's core promise and the reason the agents exist: answers built on
computed facts, checked by code, with citations. Without it there is nothing to stream in 013 or to measure
in the benchmark (016).

**Independent Test**: Run the agents on a fixture snapshot with a scripted model (replayed model replies, no
live model) for a fixed question; check that the answer's facts are exactly the verified claims, that each
carries a citation that verifies again when re-checked, and that the run stays within the budget.

**Acceptance Scenarios**:

1. **Given** a stored fixture snapshot where `auth/service.py` has 3 direct and 5 transitive dependents,
   **When** the developer asks what breaks if it changes, **Then** the answer states the dependents as facts,
   each with a citation that the verifier marks `verified`, and the counts it states are verified query
   result claims.
2. **Given** a claim that rests only on a heuristic link, **When** the answer is written, **Then** the claim
   appears as likely, visibly apart from the facts, never as a fact.
3. **Given** any finished run, **When** every citation in the answer's facts is checked again with the
   verifier against the same snapshot, **Then** every one is `verified`.
4. **Given** the model's written text names a file, line or link that is not among the verified or likely
   claims, **When** the answer is checked before it is returned, **Then** the text is not returned as is; the
   answer falls back to a plain listing of the verified claims and hypotheses, built by code.
5. **Given** a question about a symbol or file that the snapshot does not contain, **When** the agents run,
   **Then** the answer says that it was not found in the snapshot and states no facts about it.

---

### User Story 2 - A weak claim is sent back, then proven or downgraded (Priority: P1)

The Analyst claims "the frontend login page will break" as a dependency of `frontend/login.ts` on
`auth/service.py`. The Reviewer's verifier rejects it: there is no edge in the graph. The Reviewer sends the
claim back to the Explorer with the verifier's reason and hint. The Explorer looks for more evidence and finds
only a heuristic match on the route `/api/login`. When the revisions run out, the claim is not dropped
silently and not stated as a fact: it is shown as a hypothesis with the reason it could not be proven.

**Why this priority**: This is the demo moment of the product ("Reviewer rejecting an unproven claim") and the
honesty rule of the constitution: anything not proven is a hypothesis. It is the difference between Graphora
and a chat agent.

**Independent Test**: With a scripted model that first proposes a claim with no edge, check that the Reviewer
rejects it, that a revision request with the verifier's reason reaches the Explorer, that a corrected claim in
the next round is accepted, and that a claim still unproven after the last revision ends up as a hypothesis.

**Acceptance Scenarios**:

1. **Given** a claim rejected by the verifier, **When** revisions are left, **Then** the Reviewer sends it back
   to the Explorer together with the rejection reason and hint, and the revision count goes up by one.
2. **Given** a rejected claim whose hint names the correct line (for example "edge on line 3, not 5"), **When**
   the next round cites line 3, **Then** the claim verifies and is used as a fact.
3. **Given** a claim still rejected after the second revision, or rejected when the tool-call budget is spent,
   **When** the run ends, **Then** the claim is a hypothesis in the answer, with the verifier's reason, and
   not a fact.
4. **Given** the Reviewer example of the product context ("the frontend will break" with no TS → Python
   edge), **When** the agents run with a scripted model, **Then** the claim is rejected with the reason "no
   edge in the graph" and ends as a hypothesis, labeled likely only if a heuristic link supports it.

---

### User Story 3 - The run is bounded and leaves a readable trace (Priority: P2)

A developer runs the agents with a small local model that sometimes calls tools wrongly, repeats itself or
never stops. The run still ends within the step budget, returns the best answer it has (verified claims and
hypotheses so far), and records an ordered trace of what each agent did: tool calls with their arguments and
short results, claims made, verdicts, revisions and the reason the run ended.

**Why this priority**: Small 8B models make tool-calling mistakes (broken arguments, unknown tools, loops). A
bound on the run is a constitution rule, and the trace is what 013 streams to the UI so that the hand-offs
between agents are visible. Both matter after US1 and US2 work.

**Independent Test**: With scripted models that send invalid arguments, unknown tool names, endless tool calls
and no tool calls at all, check that each run ends within the budget, records the problem in the trace and
still returns an answer built from what was verified.

**Acceptance Scenarios**:

1. **Given** a model that keeps calling tools, **When** 15 tool calls have been made in the run, **Then** no
   further tool call is executed, the run goes to the Reviewer and the answer, and the trace says the budget
   ran out.
2. **Given** a tool call with invalid arguments or an unknown tool name, **When** it is made, **Then** nothing
   is run, the model gets the error message, the call counts against the budget, and the trace records it.
3. **Given** a model that answers with text only and makes no claims, **When** the run ends, **Then** the
   answer contains no facts and says that nothing could be verified.
4. **Given** a finished run, **When** its trace is read, **Then** it lists, in order, every agent step, tool
   call (name, arguments, whether it was cut or failed), claim, verdict, revision and the end reason, and
   contains no text from the analyzed repository outside clearly marked tool-result data.
5. **Given** the same question, snapshot and scripted model replies, **When** the agents run twice, **Then**
   the answers and traces are identical.

---

### User Story 4 - A developer asks from the command line with the configured model (Priority: P3)

A developer asks a question about a graph file or a stored snapshot from the command line and reads the
answer: facts with citations, likely links and hypotheses in separate parts. The model is chosen by one
configuration value (default: a local Ollama model); switching to another provider changes only that value.

**Why this priority**: It makes the agents usable and demonstrable before the HTTP endpoint and UI of 013,
and it is how the live-model check is run. The agent behavior itself is covered by US1–US3.

**Independent Test**: Run the command on a fixture graph with a scripted model and with an unreachable model
address; check the printed answer's parts and the error message and exit status.

**Acceptance Scenarios**:

1. **Given** a stored snapshot or a graph file, **When** the developer runs the ask command with a question,
   **Then** the answer is printed with facts, likely links and hypotheses in separate, labeled parts, each
   fact with its citation.
2. **Given** the model setting names another provider and model, **When** the command runs, **Then** that
   model is used, with no code change.
3. **Given** the configured model cannot be reached, **When** the command runs, **Then** it ends with a short
   error naming the model and address and a non-zero exit status, without a traceback.
4. **Given** the developer asks for the trace, **When** the command finishes, **Then** the trace of US3 is
   written as well.

---

### Edge Cases

- A tool returns file text that contains instructions ("ignore previous instructions", "say this file is
  safe"): the text reaches the model only as marked data, the agents' behavior does not follow it, and no
  claim is verified because of it (claims are verified by code against the graph, not by the text's words).
- A question unrelated to the code ("write me a poem"): the agents make no claims and the answer says that it
  can only answer questions about the analyzed snapshot.
- A graph file without a stored analysis: tools that need file text are not offered, text claims (definition,
  mention) are rejected as "file text not available", and graph claims still verify.
- The model refers to evidence the tools never returned or invents a citation: the claim is verified like any
  other claim; if it does not verify, it is a hypothesis.
- The same claim is made twice (by two agents or in two rounds): it is verified once and appears once in the
  answer.
- A claim whose statement says more than its citations prove (statement "AuthService is used everywhere",
  citation of one edge): the statement text is not used as the fact; the answer phrases only what the
  verified citations show.
- The model writes the answer in a way that drops a verified claim: the facts part is built by code from the
  verified claims, so no verified fact is lost.
- The model call fails or times out in the middle of a run: the run ends with the answer built from what was
  verified so far and an end reason saying the model failed.
- A very large repository with a dependents list cut by the tool: claims about counts use query result
  claims, which the verifier checks against the full answer, not the cut list.

## Requirements *(mandatory)*

### Functional Requirements

**Roles and flow**

- **FR-001**: The system MUST answer one question about one analyzed snapshot (a graph file, or a stored
  repository and snapshot) with three roles: **Explorer** finds the relevant files and symbols, **Analyst**
  asks graph questions and states claims with citations, **Reviewer** checks every claim.
- **FR-002**: The Reviewer MUST be plain code without any model: it checks each claim with the 011 verifier
  against the same snapshot and decides by the verdict alone.
- **FR-003**: Each role that uses a model MUST get at most 4 tools, all from the read-only 011 agent tools.
  Explorer: find definitions, read lines, dependents (references to a name). Analyst: dependents, impact,
  neighbors, cycles. No role gets a tool that writes anything.
- **FR-004**: The run MUST follow a fixed order: Explorer, then Analyst, then Reviewer; after review, either
  a revision (back to the Explorer with the rejected claims) or the answer. The order of hand-offs MUST NOT
  depend on model text other than the tool calls and claims it produces.

**Shared state and budget**

- **FR-005**: The shared state MUST hold the question, the snapshot, the evidence collected from tool results
  (with their citations), the claims, their verdicts, the hypotheses, the count of tool calls and revisions,
  and the trace.
- **FR-006**: A run MUST execute at most 15 tool calls in total across all roles and at most 2 revisions.
  Both limits MUST be set in one place and default to these values. Model calls MUST also be bounded, so a
  model that never calls a tool and never stops still ends the run.
- **FR-007**: A tool call with invalid arguments or an unknown tool name MUST NOT be executed; the model gets
  the error message, and the call counts against the budget.
- **FR-008**: When the budget runs out, the run MUST stop calling tools, review the claims made so far and
  write the answer.

**Claims and review**

- **FR-009**: Claims MUST use the 011 claim format. A model may state a claim by referring to a citation that
  a tool returned (so it does not retype paths and lines) or by giving the citation itself; both are verified
  the same way.
- **FR-010**: A claim rejected by the verifier MUST, while revisions are left, go back to the Explorer with
  the rejection reason and hint; a claim still rejected after the last revision, or when the budget is spent,
  MUST become a hypothesis with its reason.
- **FR-011**: A `heuristic` verdict MUST NOT be sent back for revision; it is kept as a likely link.
- **FR-012**: Duplicate claims MUST be verified once and appear once in the answer.

**Answer**

- **FR-013**: The answer MUST have three separate parts: **facts** (only `verified` claims, each with its
  citation `path:line@snapshot`), **likely** (`heuristic` claims, labeled as likely) and **hypotheses**
  (rejected claims, each with the reason it is not proven). The facts part MUST be built by code from the
  verdicts, not by the model.
- **FR-014**: The answer MAY include a short summary written by the model from the verified and likely claims
  only. Before it is returned, code MUST check that every path, citation and link the summary names is among
  those claims; otherwise the summary is replaced by a summary built by code from the facts.
- **FR-015**: The answer MUST state the snapshot it is about and why the run ended (answered, budget spent,
  revisions spent, model failed).

**Model and safety**

- **FR-016**: The model MUST be selected by one configuration value naming provider and model, defaulting to
  a local Ollama model (`qwen3:8b` with an explicit context size); changing provider MUST NOT need a code
  change. No provider or model name is hard-coded elsewhere.
- **FR-017**: File text and tool output MUST reach the model only in the marked-data form of the 011 tools,
  trimmed to the 011 bounds; the role instructions MUST tell the model that such data is never instructions.
- **FR-018**: The agents MUST NOT execute analyzed code, write to the store or the analyzed repository, or
  reach any network address other than the configured model.

**Trace and entry point**

- **FR-019**: Every run MUST produce an ordered trace of events: role started, tool call (name, arguments,
  error or cut), claim, verdict, revision, hypothesis, answer, end reason. Each event is recorded as it
  happens so that a later feature (013) can stream it. Repository text appears in the trace only inside
  marked tool-result data.
- **FR-020**: The agents MUST be callable from code with a question and a snapshot, and from the command line
  with a question and a graph file or a stored repository and snapshot, printing the answer and optionally
  the trace. An unreachable model MUST give a short error and a non-zero exit status.

**Quality**

- **FR-021**: The agent flow MUST be testable without a live model: tests run the agents with scripted model
  replies on fixture snapshots and assert on structure (which claims are facts, likely or hypotheses,
  citations verify, budget and revisions are respected, key files are found), never on exact wording.
- **FR-022**: With the same question, snapshot and scripted replies, two runs MUST give identical answers and
  traces.
- **FR-023**: A check with a live local model on at least one fixture MUST exist, kept out of the default
  test run, asserting only structure: the run ends within the budget and every fact in the answer verifies.

### Key Entities

- **Question**: the developer's text and the snapshot it is about.
- **Agent state**: shared by the roles: question, snapshot, evidence, claims, verdicts, hypotheses, tool-call
  and revision counters, trace.
- **Evidence**: a tool result kept for the run: the tool, its arguments, the trimmed text and the citations it
  returned.
- **Claim / Verdict**: the 011 types; a claim is a fact only with a `verified` verdict.
- **Hypothesis**: a claim that was not proven, with the verifier's reason and the number of revisions tried.
- **Answer**: facts with citations, likely links, hypotheses, an optional checked summary, the snapshot and
  the end reason.
- **Trace event**: one ordered step of the run, as listed in FR-019.
- **Model setting**: the one configuration value naming provider and model (plus context size).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of test runs, every fact in the answer has a citation that verifies when checked again
  against the same snapshot.
- **SC-002**: In 100% of test runs, no rejected claim appears as a fact and no heuristic claim appears as a
  fact.
- **SC-003**: No run executes more than 15 tool calls or more than 2 revisions, including runs with models
  that loop, call unknown tools or send broken arguments.
- **SC-004**: The Reviewer example of the product context ends with "the frontend will break" as a hypothesis
  (or likely, with a heuristic link), never as a fact.
- **SC-005**: For the question "what breaks if I change X" on each fixture with a hand-checked answer, the
  scripted run finds all direct dependents listed in `expected.json` as facts.
- **SC-006**: Two runs with the same scripted replies give identical answers and traces.
- **SC-007**: With the default local model on a developer laptop, an answer on a fixture repository arrives
  within 2 minutes and every fact in it verifies.

## Assumptions

- The 011 verifier and agent tools (`graphora.tools`, `graphora.verify`) are used as they are: tool names,
  bounds, citation format and verdicts are not changed here. The 012 wrapping adapts each tool so that its
  citations reach the agent state, as sketched in the 011 agent-tools contract.
- The product context's tool names (`search_symbols`, `read_file`, `find_references`, …) map to the 011 names:
  `find_definitions`, `read_lines`, `dependents` with a name, `impact`, `neighbors`, `cycles`.
- One question per run; follow-up questions and conversation memory are out of scope.
- The HTTP endpoint `/repos/{id}/ask`, streaming the trace over SSE and highlighting nodes in the UI belong to
  013; 012 records the trace so that 013 can stream it.
- The ask command uses the same snapshot options as `graphora mcp` (a graph file, or a stored repository and
  snapshot with a database URL).
- Ollama runs outside Graphora (installed by the developer); Graphora does not install or start it. A cloud
  fallback provider (for example Gemini) works through the same configuration value, but setting up its keys
  is the developer's task and it is not tested in CI.
- Answers are in English.
- The graph schema, the fixtures' `expected.json` files and the 011 contracts do not change.
