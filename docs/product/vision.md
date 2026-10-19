# Graphora — Vision

AI agents write code faster than people can understand it. Graphora gives people and agents a verifiable map of the code.

## Why Graphora

### Review is the new bottleneck

Most code is now written by agents, and people spend more and more time reviewing code they did not write. Knowing what a change will break becomes the key task, while chat agents answer it with text that has to be checked again.

### Reproducible facts instead of one-off answers

Coding agents explore the repository from scratch every time, and their answers can differ between runs. Graphora builds the graph deterministically: the same commit always gives the same graph, which can be saved, compared between commits and attached to a review. Dependencies, cycles and change impact are computed by algorithms, not guessed.

### Better agents, not another agent

Graph queries (reverse dependencies, impact scope, cycles, neighbours) are exposed as an MCP server, so Claude Code, Cursor and other agents can use Graphora as a tool. Our own agents are a demonstration; the product is structural memory of the code that any agent can use.

## Features

### Structure and architecture

Frontend ↔ backend bridge. Matches Python routes with TypeScript HTTP calls, links them with an edge marked as heuristic and shows the full path from a UI button to the database.

Automatic components. Louvain clustering groups files into components, an agent names them, and the map zooms from system to component, file and symbol level.

Cycle breaking. An algorithm finds the minimal set of edges to remove (feedback arc set), and an agent suggests how to do it. Recommendations only, no automatic refactoring.

### AI and agents

GraphRAG. Local embeddings of functions and classes enable search by meaning, and graph neighbours give the agent connected context instead of random fragments.

AI pull request check. Graphora compares the graph before and after a PR and shows where the PR description does not match the actual changes.

Benchmark. 30 questions with known answers compare the same model with plain grep and with Graphora via MCP: accuracy, hallucinations, tokens and time.

Natural-language graph queries. The LLM translates a request into a formal graph query, and code executes it, so the result is exact.

### Security

Attack surface map. Paths from HTTP endpoints to dangerous calls such as eval, subprocess or raw SQL, highlighted on the graph.

Vulnerable dependency reachability. Known vulnerabilities from OSV.dev are checked against the graph to show which ones are actually reachable from the code.

### Engineering

Tests to run. The graph shows which test files depend on a changed module.

Live mode. Incremental Tree-sitter parsing updates the graph on every file save.

## Hard questions

#### Why Graphora if Claude Code and Cursor exist?

They answer with text that has to be re-checked. Graphora provides a computed graph that is reproducible for every commit, and the same agents can use it through MCP.

#### What about DeepWiki?

DeepWiki generates documentation with an LLM: a narrative, not a verifiable graph. It runs in the cloud and only for public repositories. Graphora provides deterministic facts, runs locally and points to evidence.

#### Models keep getting smarter. Will Graphora become obsolete?

The more code agents write, the more important independent verification that does not depend on an LLM becomes. A graph does not hallucinate, however powerful the model is.

#### Why build your own agents if Graphora is infrastructure?

This is a course project on AI agents. It shows how agents that verify evidence work on top of deterministic tools, and the same pattern works for any external agent.

#### Isn't a small local model too weak?

That is exactly why the graph matters: an algorithm computes the facts, and the small model only phrases the answer. Everything works offline, without sending code to the cloud.
