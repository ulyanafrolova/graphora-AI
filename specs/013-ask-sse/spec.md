# Feature Specification: Ask over HTTP with a Streamed Trace

**Feature Branch**: `013-ask-sse`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "issue 013" — feature 013 from the team plan (`docs/product/team-workflow.md`,
round 5, issue #33): "Ask over HTTP: `POST /repos/{id}/ask` runs the 012 agents on one stored snapshot and
streams the answer as server-sent events. The stream carries the agent trace (tool calls, Reviewer verdicts,
revisions) and ends with the final answer: verified facts with citations, the rest marked as likely or a
hypothesis, the same as `graphora ask --json`. Agents stay read-only and the model is the one `GRAPHORA_MODEL`
setting. One answer takes 20–60 seconds on qwen3:8b, so the stream is what makes the wait usable in the UI.
Open questions for the spec: route shape next to `/api/v1` (repository and snapshot parameters), how many asks
run at once and how they share workers with analysis jobs, and what happens when the client disconnects.
Depends on 012."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a question about a stored snapshot and watch the agents work (Priority: P1)

A developer (or the Graphora web UI) has a repository analyzed and stored by the service. They send a question
about one stored snapshot, for example "What breaks if I change `loop/a.py`?". The service starts the 012
agents and, while they work, sends each step as it happens: which role started, which tool was called with
which arguments, which claims were made, the Reviewer's verdicts and revisions. When the agents finish, the
last message is the full answer: facts with citations, likely links and hypotheses, exactly as
`graphora ask --json` prints it.

**Why this priority**: This is the whole feature. An answer takes from half a minute to several minutes with a
local model; without steps arriving as they happen the UI shows nothing for that long. The trace is also the
product's demo moment: the Reviewer rejecting an unproven claim, visible live.

**Independent Test**: Start the service with a stored fixture snapshot and a scripted model, send a question,
read the stream, and check that the step messages arrive in order with the same content as the trace of a
direct `ask` call, and that the last message equals the direct `ask` result.

**Acceptance Scenarios**:

1. **Given** a stored snapshot and a working model, **When** a client asks a question, **Then** the response
   starts at once (before the first model reply) and delivers one step message per trace event, in order,
   numbered 1, 2, 3, …, followed by one final answer message, and then the response ends.
2. **Given** the same question, snapshot and model replies, **When** the answer is requested over HTTP and
   with `graphora ask --json`, **Then** the final answer message and the step messages carry the same content
   as the command's output.
3. **Given** a question that the agents answer with a rejected claim, **When** the stream is read, **Then** the
   verdict, hypothesis and revision steps appear in the stream before the final answer, and the claim appears
   in the final answer only as a hypothesis.
4. **Given** a run in which the model fails part-way, **When** the stream ends, **Then** the final answer
   message still arrives, with the end reason "model failed", the facts verified so far, and the reason the
   model failed.

---

### User Story 2 - Bad requests are refused before any work starts (Priority: P1)

A client sends a question for a repository or snapshot that is not stored, an empty or overlong question, or
malformed input. The service answers at once with the same kind of error the rest of the HTTP API uses, and
starts no agents and no model calls.

**Why this priority**: Starting a minutes-long model run for a request that cannot succeed wastes the only
local model; clear errors are needed for the UI to show the right message.

**Independent Test**: Send each kind of bad request and check the status and error body, and that the model
was never called.

**Acceptance Scenarios**:

1. **Given** a repository name that is not stored, **When** a client asks, **Then** the answer is "not found"
   with the message "repository not found: <name>", as `GET /api/v1/graph` gives.
2. **Given** a stored repository but an unknown snapshot, **When** a client asks, **Then** the answer is "not
   found" with "snapshot not found: <repository> <snapshot>".
3. **Given** an empty question, a question longer than 2,000 characters, a missing field, an unknown field or a
   body that is not a JSON object, **When** a client asks, **Then** the answer is "bad request" with a message
   naming the problem.
4. **Given** the configured model setting names an unknown provider or a provider whose package is missing,
   **When** a client asks, **Then** the answer is "service unavailable" with the model message (the same text
   as `graphora ask` prints), and no stream is started.

---

### User Story 3 - The local model is shared fairly (Priority: P2)

The service runs on a developer laptop with one local model. Two people (or two browser tabs) ask at the same
time. The service runs at most a fixed number of asks at once (default one); a request beyond that is refused
at once with "busy" and a hint to retry later, rather than queuing silently for minutes. Analysis jobs keep
running on their own workers and are not blocked by asks, and asks are not blocked by analysis jobs.

**Why this priority**: An 8B model on a laptop serves one answer at a time; two parallel runs make both slower
than running them one after another, and a hidden queue looks like a hang in the UI.

**Independent Test**: Hold one ask open with a scripted model that waits, send a second ask, and check that it
is refused as busy while an analysis job still starts and finishes.

**Acceptance Scenarios**:

1. **Given** one ask running and the limit of one, **When** another ask arrives, **Then** it is refused at once
   with "busy", a retry hint, and no model call.
2. **Given** the first ask finished or its client disconnected, **When** a new ask arrives, **Then** it is
   accepted.
3. **Given** an ask running, **When** an analysis job is submitted, **Then** the job starts and runs on the
   analysis workers as before.
4. **Given** the service was started with a higher ask limit, **When** that many asks run at once, **Then**
   all are accepted and the next one is refused as busy.

---

### User Story 4 - A client that goes away stops the work (Priority: P2)

A user closes the browser tab in the middle of an answer. The service notices that nobody is reading the
stream and stops the agents at the next step, so the model is free for the next question within one model
call, not after the whole run.

**Why this priority**: Without it a closed tab keeps the only model busy for minutes and every new question is
refused as busy.

**Independent Test**: Start an ask with a scripted model that answers slowly, disconnect after the first step,
and check that no further tool or model calls are made after the step in progress and that a new ask is
accepted.

**Acceptance Scenarios**:

1. **Given** a running ask, **When** the client disconnects, **Then** the agents make no new model call or tool
   call after the step that is running, and the ask slot is freed.
2. **Given** a disconnected ask, **When** its run stops, **Then** nothing is written to the store and nothing
   is left running in the service.

---

### User Story 5 - Long silences do not break the connection (Priority: P3)

A model call can take more than a minute with nothing to report. Proxies and browsers drop connections that are
silent for too long. The service sends a small keep-alive message during long silences so the stream stays
open, and a client can ignore these messages.

**Why this priority**: It only matters when a proxy sits in between or a model call is very slow, but then
the answer is lost.

**Independent Test**: With a scripted model that waits longer than the keep-alive interval, check that
keep-alive messages arrive during the wait and are not counted as steps.

**Acceptance Scenarios**:

1. **Given** no step for 15 seconds, **When** the stream is open, **Then** a keep-alive message is sent, and
   again every 15 seconds until the next step.
2. **Given** a client reading only step and answer messages, **When** keep-alive messages arrive, **Then** they
   carry no data and do not change the step numbering.

---

### Edge Cases

- A snapshot stored without file text (for example an older stored analysis): the agents run with the tools
  they can use; text claims become hypotheses "file text not available", as in 012.
- The service is shutting down while an ask runs: open streams are closed after a short grace period and their
  runs are stopped like a disconnected client; such a stream ends without a final answer.
- An unexpected internal error during the run (not a model failure): the stream ends with an error message
  carrying a short reason and no traceback, and the ask slot is freed.
- The question contains text that looks like instructions or markup: it is passed to the agents as the
  developer's question, never echoed into the stream except inside the final answer's question field.
- A client sends the same question twice in a row: each request is a separate run; there is no cache of
  answers.
- A client asks while the model is still loading (first call after start): the first step messages arrive as
  soon as they happen; the keep-alive covers the wait.
- A request that is refused (not found, bad request, busy, model setting broken) never opens a stream: the
  client gets one normal error response.

## Requirements *(mandatory)*

### Functional Requirements

**Request**

- **FR-001**: The service MUST accept a question about one stored snapshot named by repository and snapshot id,
  in the style of the existing `/api/v1` endpoints, with the question as text of at most 2,000 characters
  after trimming.
- **FR-002**: The service MUST validate the request before starting any work: known fields only, non-empty
  question within the limit, repository and snapshot stored. Errors MUST use the existing API error format and
  messages ("repository not found: …", "snapshot not found: … …", bad request with the field named).
- **FR-003**: The service MUST build the model from the one model setting of 012 and refuse the request as
  "service unavailable" with the model message when the setting cannot be used, before any stream is opened.

**Stream**

- **FR-004**: An accepted request MUST be answered with an event stream that sends, in order: one step
  message per trace event of the run as it happens (same fields as the 012 trace event), then exactly one
  final answer message with the same content as `graphora ask --json` (answer, trace and, for a failed model,
  the reason), then ends.
- **FR-005**: Step messages MUST be sent when the event happens, not collected until the end; the first step
  message MUST be sent before the first model reply arrives.
- **FR-006**: The stream MUST carry no file content and no model text in step messages, as the 012 trace;
  model text appears only in the final answer's checked summary.
- **FR-007**: During silences longer than 15 seconds the service MUST send keep-alive messages that carry no
  data and are not steps.
- **FR-008**: An unexpected internal error during a run MUST end the stream with one error message (short
  reason, no traceback) instead of a final answer.

**Concurrency and lifetime**

- **FR-009**: The service MUST run at most a configured number of asks at once (default 1), separate from the
  analysis job workers; a request beyond the limit MUST be refused at once as "busy" with a retry hint and no
  model call.
- **FR-010**: Asks MUST NOT block analysis jobs and analysis jobs MUST NOT block asks.
- **FR-011**: When the client disconnects, the run MUST stop at the next step: no new model call or tool call
  is started after the one in progress, and the ask slot MUST be freed when it stops.
- **FR-012**: When the service shuts down, running asks MUST be stopped the same way.

**Safety**

- **FR-013**: Asks MUST be read-only: they read the stored snapshot and write nothing to the store, the work
  folder or the analyzed repository, and reach no network address other than the configured model.
- **FR-014**: Each ask MUST use its own store connection for the run, so a long ask does not hold up the other
  read endpoints.

**Quality**

- **FR-015**: Tests MUST run without a live model (scripted replies) and assert on structure: order and
  numbering of steps, equality of the final answer with a direct `ask` call, error statuses, busy refusals,
  stop on disconnect.
- **FR-016**: The HTTP contract of the new endpoint, its messages and errors MUST be documented next to the
  existing API contracts, with a curl example.

### Key Entities

- **Ask request**: repository, snapshot id and question text.
- **Step message**: one trace event of the 012 run, sent as it happens, numbered from 1.
- **Final answer message**: the 012 run result (answer, trace, failure reason), the last message of a stream.
- **Error message**: the last message of a stream that ended by an unexpected internal error.
- **Keep-alive message**: an empty message sent during silences.
- **Ask slot**: one of the configured number of asks that may run at once.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The first step message reaches the client within 1 second of an accepted request, before the
  model answers for the first time.
- **SC-002**: For the same question, snapshot and scripted model replies, the final answer over HTTP is
  identical to the `graphora ask --json` output in 100% of test runs.
- **SC-003**: 100% of refused requests (not found, bad request, busy, model setting unusable) are answered
  within 1 second and start no model call.
- **SC-004**: After a client disconnects, at most one model call that was already running completes; no new
  model or tool call starts, and a new ask is accepted within the time of that one call.
- **SC-005**: An analysis job submitted while an ask runs starts within the same time as when no ask runs.
- **SC-006**: A stream silent for 60 seconds receives at least 3 keep-alive messages and stays open.

## Assumptions

- The route follows the existing API (`/api/v1`, repository and snapshot named in the request) instead of the
  product context's `/repos/{id}/ask`; the product context is updated to match.
- The service is the existing `graphora serve` on 127.0.0.1, without authentication, like the other
  endpoints; exposing it beyond the local machine is out of scope.
- The ask limit is a `serve` option next to the job options; analysis jobs keep their own `--workers` and
  queue. Asks are not queued: a busy refusal is clearer for a single local model than a hidden wait.
- The run uses the 012 agents and limits unchanged (15 tool calls, 2 revisions, summary on); per-request
  options (model choice, no summary) are out of scope: the model is the service's one setting.
- Stopping a run on disconnect needs the 012 agents to accept a stop signal checked between steps; adding it
  is part of this feature and does not change 012 behaviour when no stop is requested.
- Answers are not stored and there is no history of questions; the UI keeps what it shows.
- Highlighting nodes on the graph is done by the UI (feature 015 and the frontend) from the citations in the
  final answer; this feature only delivers them.
- No change to the graph schema, the store schema, the 011 verifier, the 011 tools or the MCP server.
