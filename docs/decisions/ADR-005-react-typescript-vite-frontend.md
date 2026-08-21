# ADR-005: React, TypeScript, and Vite frontend

Status: Accepted on 2026-08-21

## Context

Generation Contract v1 and HTTP API Mapping v1 already expose every operation required by the local single-user MVP. The remaining client must let a user discover enabled capabilities, submit a text-to-video job, follow truthful status, cancel active work, inspect failures, and preview or download successful output. It must remain independent of the Python application and must not pull model execution into a browser or API process.

The MVP needs one responsive application screen, not server-side rendering, search-engine indexing, nested navigation, offline synchronization, or a shared component platform. Adding routing, client caches, global stores, or a component kit before those needs exist would create a second application architecture around a small stable API.

## Decision

- Create a separate top-level `frontend/` workspace. It is a client of `/api/v1`; it does not import Python modules, database types, backend adapters, or files below `src/video_app/`.
- Use React with function components and hooks, TypeScript in strict mode, and Vite for development and production builds.
- Keep API transport in one typed client built on the browser's native `fetch`. Preserve the API's `snake_case` wire fields, URL-encode opaque identifiers and query values, accept `AbortSignal`, and translate non-success responses into the safe public error shape.
- Use relative `/api/v1` URLs. Vite proxies `/api` to `http://127.0.0.1:8000` during local development. The proxy is a development convenience, not a deployment or CORS decision.
- Use React-owned local state and effects. Do not add a router, query/cache library, global state library, UI/component kit, Tailwind, CSS-in-JS runtime, or HTTP client library.
- Use plain CSS governed by the root `DESIGN.md`. The interface remains one screen and uses semantic HTML, visible keyboard focus, reduced-motion support, and non-color status labels.
- `@chenglou/pretext` is the only approved non-React production helper. Its use is restricted to text measurement and layout. It does not own controls, styles, remote data, or application state and is not a component kit.
- Poll existing GET operations every 2.5 seconds while any displayed or selected job is `queued` or `running`. Permit at most one refresh request in flight, skip scheduled cycles while the document is hidden, stop when no active job remains or the component unmounts, and abort in-flight work on unmount. A failed cycle shows safe connection feedback and waits for the next cadence or manual refresh. There is no elapsed-time cutoff because generation may run for hours.
- Keep frontend quality checks independent and deterministic: strict TypeScript, ESLint with zero warnings, Prettier verification, Vitest, Testing Library with jsdom, and a production Vite build. Browser tests mock the public API and require neither PostgreSQL nor a GPU.

## Boundary and ownership

The frontend owns presentation state, browser interaction, accessibility, responsive layout, and mapping the stable HTTP representation into visible controls. FastAPI remains the public transport owner. PostgreSQL remains the authoritative job store. The worker remains the only process that invokes a generation backend.

The frontend may not:

- change or infer job states beyond the five contract values;
- fabricate progress, completion estimates, defaults, or retry behavior;
- expose filesystem paths, backend arguments, or runtime configuration;
- add authentication, cookies, CORS policy, uploads, deletion, prompt rewriting, or new API fields;
- run generation, persist a second job record, or treat browser state as authoritative.

Changes to Generation Contract v1, HTTP API Mapping v1, authentication, deployment hosting, or backend defaults remain separate decisions. Replacing this frontend stack or adding one of the excluded architectural libraries requires explicit approval and a superseding ADR.

## Alternatives considered

### Next.js or another full-stack React framework

Server rendering, file-based routing, and a second server runtime do not serve the local single-screen MVP. They would blur the accepted FastAPI boundary and introduce deployment decisions that remain intentionally open.

### Server-rendered FastAPI templates

Templates would reduce the number of toolchains, but interactive polling, capability-driven controls, cancellation, and media state would move browser presentation concerns into the API layer. A separate client keeps the current dependency direction intact.

### React with router, query cache, global store, and component kit

These tools are useful when navigation, shared remote caches, or a broad design system justify them. The v1 screen has one API surface and a small state graph, so native fetch and React state are easier to inspect, test, and replace.

### Vue or Svelte

Both can implement the contract. React was explicitly approved for this repository and aligns with the accepted Testing Library workflow. The choice is local to `frontend/` and does not change the API.

## Consequences

- Frontend development adds a pinned Node dependency graph and lockfile alongside the Python project.
- The browser and Python application can evolve independently as long as Generation Contract v1 remains compatible.
- Local development runs Vite and FastAPI as separate processes, with Vite forwarding only `/api` requests.
- Poll scheduling, cancellation, and error handling remain visible first-party code rather than hidden library behavior.
- TypeScript types duplicate the public wire contract, so contract-focused client tests are required to detect drift.
- JSON cannot preserve every signed 64-bit seed exactly in JavaScript. Manual UI input is restricted to safe integers, and unsafe-range server seeds are acknowledged without displaying a rounded number. Exact reuse requires a future versioned contract representation.
- Production hosting, authentication, and CORS remain undecided and are not implied by the Vite development proxy.

## Related documents

- [Frontend UI Specification v1](../specifications/frontend-ui-v1.md)
- [Generation Contract v1](../contracts/generation.md)
- [HTTP API Mapping v1](../specifications/http-api-v1.md)
- [Design System](../../DESIGN.md)
