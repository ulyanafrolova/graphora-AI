# http-bridge fixture

A small full-stack repository for the HTTP bridge (specs/015-http-bridge). The backend (`backend/`) declares FastAPI
and Flask routes; the frontend (`frontend/`) calls them with `fetch` and `axios`. `expected.json` next to `repo/`
is written by hand from these files.

| File | Scenarios |
|---|---|
| `backend/app/items.py`, `frontend/src/items.ts` | US1: literal GET and POST, Flask route, the same call on two lines |
| `backend/app/users.py`, `frontend/src/users.ts` | US2: `{id}` and `<int:id>` parameters, template and `+` calls, `/users/me` vs `/users/{id}`, query string, multi-method Flask route |
| `backend/app/main.py`, `backend/app/routers/orders.py`, `frontend/src/orders.ts` | US3: `APIRouter(prefix)` + `include_router(prefix)` through an import, a base constant `API` |
| `backend/app/blueprints.py`, `backend/app/legacy.py` | US3: Flask blueprint prefix, and `register_blueprint(url_prefix=…)` replacing it (`/old` → `/reports`) |
| `backend/app/health_a.py`, `backend/app/health_b.py`, `frontend/src/misc.ts` | US4: dynamic URLs, a route in two files (ambiguous), no route (not found), another host (dropped), a method in a variable |
