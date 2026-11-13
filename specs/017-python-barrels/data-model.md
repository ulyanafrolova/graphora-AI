# Data Model: Python Barrel Following

## Edge (changed)

| Field | Change |
|---|---|
| `alias` | Now also allowed on `imports` edges from the Python adapter: the local name bound by `as`, when it differs from the default (research § R2). Still allowed on `reexports` and `using_alias` edges as before. |

Validation (model and schema): `alias` present → `type` is `reexports`, or `directive` is `using_alias`, or
(`type` is `imports` and `extractor` starts with `python-adapter@`). A Python `alias` is never equal to the
edge's `symbol`.

## ImportRecord (adapter, internal)

`aliases: tuple[str | None, ...]` next to `names`: the `as` name of each imported name, or `None`.

## Derived barrel link (unchanged shape)

`Link(source=importer, target=defining file, edges=import edges, via=chain edges, confidence, type_only)`;
for Python the `via` edges are `imports` edges instead of `reexports`.

## Document

`schema_version`: 7. Extractors: `python-adapter` 0.4.0.
