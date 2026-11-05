# Contract: Python Query API

The one graph query layer (constitution VII). HTTP (later), MCP (006), agent tools and the verifier (008)
call these functions and never reimplement them. Types: [data-model.md](../data-model.md).

```python
# graphora.graph.load
class InvalidGraph(Exception): message: str
def loads(data: bytes) -> GraphDocument          # R2; raises InvalidGraph

# graphora.graph.queries
class NodeNotFound(Exception): target: str; status: str
def index(doc: GraphDocument) -> GraphIndex      # build once, reuse for many queries
def resolve(ix: GraphIndex, target: str) -> str  # R10; returns a node id or raises NodeNotFound

def dependencies(ix, target: str, *, include_type_only: bool = True, limit: int | None = None) -> Answer
def dependents(ix, target: str, *, symbol: str | None = None, include_type_only: bool = True,
               follow_barrels: bool = False, limit: int | None = None) -> Answer
def impact(ix, target: str, *, max_depth: int | None = None, include_type_only: bool = True,
           follow_barrels: bool = False, limit: int | None = None) -> Answer
def neighbors(ix, target: str, *, include_type_only: bool = True, limit: int | None = None) -> Answer
def cycles(ix, *, include_type_only: bool = True, limit: int | None = None) -> Answer
def key_files(ix, *, include_type_only: bool = True, limit: int = 10) -> Answer

# graphora.graph.results
def dumps(answer: Answer) -> bytes               # canonical JSON (R11)
def render_text(answer: Answer) -> str           # readable text for the CLI
```

Rules:

- `include_type_only=False` leaves type-only edges out (FR-013).
- `symbol` keeps only edges whose `symbol` equals it (for re-exports also the alias). With
  `follow_barrels=True` the filter applies to the symbol name at the import edge.
- `limit=None` means no limit. `limit` must be ≥ 0; `max_depth` must be ≥ 1.
- Functions are pure: the same `GraphIndex` and arguments give an equal `Answer`, and `dumps` gives identical
  bytes. No function reads files, the network or the clock.
- `impact` target may be any node kind; dependents of an `ext:` node are the files importing it, then
  transitive dependents of those files. `cycles` and `key_files` consider only `file:` nodes.
