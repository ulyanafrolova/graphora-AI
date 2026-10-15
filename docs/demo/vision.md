# Graphora — Vision

AI agents write code faster than people can understand it. Graphora gives people and agents a verifiable map of the code.

## Why Graphora

### The bottleneck has moved to review

Most code is now written by agents. People write less and review more code they did not write. The key question becomes "what will break if this PR is merged?", and a chat agent answers it with text that has to be checked again.

Agents generated 40 files overnight. You are the reviewer. What exactly did they touch?

### One-off answers vs. reproducible facts

Claude Code or Cursor explore the repository from scratch every time: grep, file reads, tokens. The answer lives in a chat and can differ the next time you ask.

Graphora builds the graph deterministically: the same commit always gives the same graph. The result can be saved, compared between commits, shared with the team and attached to a review.

Reverse dependencies, cycles and change impact are computed by algorithms, not guessed. For a grep-based agent this is slow and expensive, especially in large repositories.

### We make agents better, not compete with them

Graph queries such as reverse_dependencies, impact_scope, detect_cycles and get_neighbors are exposed as an MCP server. Claude Code, Cursor or any other agent can use Graphora as a tool.

Our own agents are a demonstration. The actual product is structural memory of the code that any agent can use.

## Features

Estimated effort for a team of three is given in brackets.

### Structure and architecture

Frontend ↔ backend bridge (1–2 weeks). Graphora matches routes in Python, such as @app.post("/api/login"), with calls in TypeScript, such as fetch("/api/login"), and links them with an edge marked as heuristic. Regular analyzers see two separate worlds; Graphora shows the full path from a UI button through the API and service to the database.

Automatic layers and components (under a week). The graph is clustered with the Louvain algorithm from NetworkX, and an agent names the clusters: Authentication, Payments, UI components. The map zooms by level: system, component, file, symbol. Without this, large graphs turn into a hairball.

Cycle breaking assistant (1–2 weeks). The algorithm finds the minimal set of edges whose removal breaks a cycle (feedback arc set), and an agent explains how to do it: extract an interface or move a function. This is a recommendation only; there is no automatic refactoring.

### AI and agents

GraphRAG: semantic search plus graph (1–2 weeks). Every function and class gets an embedding from a local model, for example nomic-embed-text via Ollama. A question like "where are payment retries handled?" finds the code even if those words are not in it. Found nodes are expanded with their graph neighbours, so the agent gets connected context instead of random code fragments.

Checking PRs written by AI agents (more than 2 weeks). An agent opens a PR described as "only changed the login logic". Graphora compares the graphs before and after and finds that billing is also affected and a new dependency was added. The result: the PR description does not match the changes in 3 places.

Benchmark: agents with and without the graph (1–2 weeks). A set of 30 questions with known correct answers on test repositories. The same model is compared with plain grep and with Graphora via MCP, measuring accuracy, hallucination rate, tokens and time. This turns "we think it is better" into "we measured it".

Natural-language graph queries (1–2 weeks). "Show all frontend modules that transitively reach the database." The LLM translates the question into a formal graph query, and code executes it, so the result is exact, not generated.

### Security

Attack surface map (1–2 weeks). HTTP endpoints are treated as entry points, and Graphora finds paths from them to dangerous calls: eval, subprocess, SQL built from strings, file writes. For example, os.system() is reachable from POST /upload in 3 steps. These paths are highlighted in red on the graph.

Vulnerable dependency reachability (1–2 weeks). Libraries from requirements.txt and package.json are checked for known vulnerabilities with the free OSV.dev API. The graph then shows whether the vulnerable code is actually used and from which modules: 12 vulnerable packages, but only 2 actually reachable.

### Engineering

Which tests to run (under a week). The graph shows which test files transitively import a changed module: you changed auth/service.py, so run these 7 of 300 tests.

Live mode (more than 2 weeks). Graphora connects to a local folder and updates the graph within milliseconds on every file save, using incremental Tree-sitter parsing. The map lives together with the code.

## Hard questions

Why use Graphora if Claude Code and Cursor exist?
They answer with text that has to be re-checked. Graphora provides a computed graph that is reproducible for every commit, and the same agents can use it through MCP.

What about DeepWiki?
DeepWiki generates LLM documentation: a narrative, not a verifiable graph. It runs in the cloud and only for public repositories. Graphora provides deterministic facts, runs locally and highlights evidence.

Models keep getting smarter. Will Graphora become obsolete?
The more code agents write, the more important independent verification that does not depend on an LLM becomes. A graph does not hallucinate, no matter how powerful the model is.

Why build your own agents if Graphora is infrastructure?
This is a course project on AI agents. It shows how agents with evidence checking work on top of deterministic tools, and the same pattern works for any external agent.

Isn't a small local model too weak?
That is exactly why the graph matters: an algorithm computes the facts, and the small model only phrases the answer. Everything works offline, without sending code to the cloud.
