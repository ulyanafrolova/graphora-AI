# http-bridge fixture

A small full-stack repository for the HTTP bridge (specs/015-http-bridge). The backend (`backend/`) declares
FastAPI and Flask routes; the frontend (`frontend/`) calls them with `fetch` and `axios`. Each file covers the
scenarios named in its first comment; `expected.json` next to `repo/` is written by hand from these files.
