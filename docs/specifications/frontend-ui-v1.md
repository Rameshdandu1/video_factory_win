# Frontend UI Specification v1

Status: Accepted, implemented, and verified on 2026-08-21

This specification defines the local single-user browser client selected by ADR-005. It consumes Generation Contract v1 and HTTP API Mapping v1 without changing either contract. It introduces no API fields, schemas, authentication, CORS policy, generation defaults, prompt processing, storage behavior, or model-runtime behavior.

## Scope

The v1 frontend is one responsive screen that supports the complete MVP workflow:

1. Check API health and discover enabled model capabilities.
2. Submit one text-to-video request with a prompt and supported settings.
3. List recent jobs newest first and inspect a selected job.
4. Refresh truthful queued or running state without inventing progress.
5. Cancel an active job through the idempotent cancellation operation.
6. Preview and download a successful MP4.
7. Present safe validation, queue, connection, and generation failures.

The frontend is not an administrative console. Authentication, multiple users, uploads, image-to-video, editing, output deletion, prompt enhancement, billing, sharing, analytics, and deployment hosting remain out of scope.

## Application boundary

First-party browser code lives below a separate top-level `frontend/` directory. Its only application dependency is the public HTTP API. It must not import from `src/video_app/`, connect to PostgreSQL, inspect the artifact root, invoke Wan2.1, or read application environment files.

Production browser dependencies are limited to React, React DOM, and `@chenglou/pretext`. Pretext may perform text measurement and layout only; it must not become a control library, design system, remote-data cache, or state owner. The application uses no router, query/cache library, global state library, UI/component kit, Tailwind, CSS-in-JS runtime, Axios, or equivalent transport wrapper.

All browser requests use relative `/api/v1` URLs. During local development, Vite proxies `/api` to `http://127.0.0.1:8000`. The backend is not changed to accommodate the client: no CORS middleware, frontend-specific endpoint, cookie, or schema is added.

## Source ownership

The frontend keeps responsibilities narrow:

```text
frontend/
  src/
    api/          snake_case HTTP contracts, native-fetch client, client tests
    components/   composer, selected-job detail, recent-job queue, status badge
    hooks/        workspace orchestration and Pretext-backed layout behavior
    lib/          display-only formatting for status, media, dates, IDs, and seeds
    test/         shared Vitest/Testing Library setup
    App.tsx       screen composition and local status-filter state
    main.tsx      React composition entry point
    styles.css    DESIGN.md tokens, responsive layout, component states
```

Tests may be colocated as `*.test.ts` or `*.test.tsx`. New component modules are created only when a UI unit gains independent behavior or reuse; v1 does not establish a second component framework.

## API operations

The UI uses only the accepted operations below.

| User behavior       | Method and path                     | Client behavior                                                                           |
| ------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------- |
| Check connectivity  | `GET /api/v1/health`                | Show connected state only for `{ "status": "ok" }`                                        |
| Discover controls   | `GET /api/v1/models`                | Use enabled capabilities as the sole source of model, resolution, and frame-count options |
| Submit generation   | `POST /api/v1/jobs`                 | Send Generation Contract v1 fields and select the returned queued job                     |
| Load recent jobs    | `GET /api/v1/jobs`                  | Request newest-first pages, default limit 20, and preserve the opaque `next_cursor`       |
| Filter jobs         | `GET /api/v1/jobs?status=...`       | Reset pagination when the exact status filter changes                                     |
| Inspect or refresh  | `GET /api/v1/jobs/{job_id}`         | URL-encode the opaque ID and replace the matching client snapshot                         |
| Cancel active work  | `POST /api/v1/jobs/{job_id}/cancel` | Disable duplicate cancellation while pending and accept the returned current state        |
| Preview or download | `GET /api/v1/jobs/{job_id}/output`  | Use the successful result's relative `download_url`; do not construct a host path         |

The API client preserves `snake_case` JSON rather than maintaining a second camel-case wire model. It URL-encodes identifiers, cursor values, and status filters; accepts `AbortSignal`; sends JSON with the correct content type; and rejects a response that cannot be interpreted as the documented success or safe error representation. It never renders or logs raw response bodies or exception strings.

## Bootstrap and screen states

On mount, the client starts one combined health-and-capability load plus a separate first-page recent-job load. A failure produces a safe connection banner and leaves manual recovery available. Submission stays disabled without enabled capabilities, and an unavailable job page does not blank the composer or selected-job region.

The screen has these visible regions:

- a header with the product name, API connection state, and manual **Refresh jobs** action, which is disabled and reads **Refreshing…** while its request is in flight;
- a generation composer with prompt and capability-derived settings;
- a recent-job list with exact status labels and newest-first ordering;
- a selected-job detail area containing request metadata, truthful execution state, cancellation, failure information, and successful media.

There is no client-side route in v1. Selecting a job updates in-memory presentation state. Reloading the page returns to the recent-job screen and asks the API for authoritative state.

## Generation composer

The composer exposes:

- a required prompt textarea with a visible 2,000-character limit;
- enabled logical model choices from `/api/v1/models`;
- complete resolution pairs formatted as `width × height`;
- supported frame counts for the selected model;
- an optional manual seed;
- one primary **Generate video** action.

The client never invents a model, resolution, or frame count. Controls derive only from enabled capabilities. If exactly one valid option exists, the UI may select it; otherwise the user selects explicitly. Changing the model resets incompatible dependent choices. `mode` remains exactly `text_to_video`.

Prompt validation uses trimmed length. Submission removes surrounding whitespace as the canonical normalization already required by Generation Contract v1, but does not enhance, otherwise rewrite, save, or log the prompt. The server remains authoritative for validation and normalization. The UI does not generate an omitted seed.

JSON and JavaScript numbers cannot preserve every signed 64-bit integer. Manual seed input is therefore limited to integer values from `Number.MIN_SAFE_INTEGER` through `Number.MAX_SAFE_INTEGER`. The UI blocks invalid or unsafe manual values and explains that leaving the field blank lets the server generate and persist a seed across the full public contract. This is a browser-input limitation only; Generation Contract v1 remains signed 64-bit.

The API may return a server-generated signed 64-bit seed outside JavaScript's safe-integer range. The UI accepts the job and all other fields, but displays **Stored by server** instead of an imprecise numeric seed and does not offer that value for reuse. Exact browser display or reuse of the full seed range requires a future versioned contract representation, likely a decimal string; Frontend UI v1 does not change the current API.

While submission is in flight, the primary action is disabled and indicates pending work. A double click, Enter key repeat, or rerender must not create a second request. On `202`, the returned job is selected and merged into the recent list. On failure, the entered form remains available for correction or retry.

## Job list and selection

Each button-backed job row shows enough information to distinguish work without exposing internals:

- the stable visible status label and created timestamp on the first line;
- a prompt excerpt clamped to two lines in the local single-user view;
- request model identifier, resolution, frame count, and resolved seed;
- a labeled created or completed timestamp and compact job ID.

Visible badge labels map `queued` to **Queued**, `running` to **Running**, `succeeded` to **Ready**, `failed` to **Failed**, and `cancelled` to **Cancelled**. Status filters send the exact API values `queued`, `running`, `succeeded`, `failed`, or `cancelled`; **All jobs** sends no status parameter. **Load older jobs** uses `next_cursor`, appends without duplicate IDs, and disappears when the cursor is null. Cursor contents remain opaque.

Selection never changes server state. The first page selects its first item when no job is already selected. Activating a row selects its list snapshot immediately, then reads the authoritative job resource and merges that response by ID. A header refresh replaces the current first filtered page in the API's newest-first order, so previously loaded cursor pages are no longer displayed. It refreshes the selection from that page; if an active selected job is outside the page, the same refresh also reads that job directly. The browser does not keep jobs in local storage or treat its list as durable.

## Truthful status and polling

Queued and running jobs trigger bounded polling with these exact rules:

- cadence is 2.5 seconds while any displayed or selected job is `queued` or `running`;
- at most one refresh request is in flight at any time;
- a scheduled cycle is skipped while `document.visibilityState === "hidden"`;
- polling stops when no displayed or selected job is active;
- unmount clears the schedule and aborts an in-flight request;
- a failed cycle shows safe connection feedback, then waits for the next cadence or manual retry;
- polling calls existing GET operations only and never resubmits or retries a generation job;
- there is no overall elapsed-time cap because a real generation may run for hours.

If `progress` is null, running state is indeterminate and shows no percentage or estimated completion time. If the API supplies a valid progress object, the UI may show completed units, total units, and the safe stage label. It must not extrapolate an ETA.

The browser remains secondary to PostgreSQL. A refresh response replaces local status even when it contradicts an older optimistic view.

## Cancellation

The **Cancel generation** action is available only for `queued` or `running` jobs. It calls the existing idempotent cancel endpoint once, disables while pending, and renders the returned job representation.

A running job may remain `running` after the request while cooperative cleanup completes. The UI therefore changes the action to a non-blocking cancellation-requested state and continues normal polling; it must not label the job `cancelled` until the API does. Terminal jobs never show an active cancellation control.

## Success and output

A succeeded job with a result renders:

- a native `<video controls>` preview using the relative `download_url`;
- an **MP4 ready** summary and normal **Download video** link to the same URL;
- request model, resolution, frame count, seed, created time, and runtime metadata;
- result byte size, duration when present, and compact checksum.

The UI never exposes an artifact path or assumes a filename. If the browser reports a media-load error for the preview, the job, result metadata, and download link remain visible. The detail area adds the safe alert **This video output is currently unavailable. Refresh the job before trying again.** The header's **Refresh jobs** action remains available; the client does not render a raw media or response error.

## Failures and recovery

Public `ApiError` and job `failure` messages are the only server messages shown. The UI may display safe code, message, retryability, correlation ID, job ID, and field names. It must not display a raw `Response`, stack trace, local path, request body, or caught exception text.

Field names from `INVALID_REQUEST` may focus or annotate matching controls. `QUEUE_FULL` keeps the form and offers a later resubmission. A retryable job failure means the user may create a new job; the UI must not retry the original automatically. `JOB_NOT_FOUND` removes no unrelated local record. Connection failures use a fixed client-owned message and a manual retry action.

## Accessibility and responsive behavior

The implementation follows `DESIGN.md` and targets WCAG 2.2 AA behavior for the v1 screen:

- every control has a programmatic label and usable keyboard order;
- focus is visible and moves to the first actionable validation problem after a rejected submission;
- status and errors are expressed in text, not color alone;
- connection and job-state changes use restrained `aria-live` announcements without repeating on every unchanged poll;
- controls meet a 44-by-44 CSS-pixel target where practical;
- native video controls remain keyboard accessible;
- motion respects `prefers-reduced-motion`;
- the desktop workspace stacks into one reading column on narrow viewports without horizontal page scrolling.

## Verification

Frontend checks are run from `frontend/` and must pass before the milestone is complete:

```powershell
npm run format
npm run lint
npm run typecheck
npm test
npm run build
```

Vitest and Testing Library tests cover at minimum:

- API paths, URL encoding, methods, body shape, safe errors, and request abortion;
- bootstrap loading, independent failure states, and manual recovery;
- capability-derived options, safe manual seed validation, and non-numeric presentation of an unsafe-range server seed;
- one-request submission and preservation of form data on failure;
- recent-job filtering, selection, pagination merge, and refresh;
- queued/running indeterminate state and reliable progress when present;
- polling cadence, no overlap, hidden-document skip, terminal stop, and unmount cleanup;
- idempotent cancellation presentation and running-cleanup state;
- successful video preview/download and unavailable output;
- safe API/job error rendering without raw internal details;
- keyboard-accessible names for primary controls and status regions.

Tests mock `fetch` and use jsdom. They require no live API, PostgreSQL, worker, model weights, GPU, or network. Backend integration tests remain authoritative for HTTP behavior; frontend tests verify that the client consumes that behavior correctly.

## Acceptance criteria

Frontend UI v1 is complete when:

- a developer can run FastAPI and Vite locally without enabling CORS;
- every in-scope MVP action is available from the single screen;
- model controls contain only API-advertised capability combinations;
- active jobs refresh under the bounded polling rules and never show fabricated progress;
- cancellation, failures, preview, and download remain truthful to the returned job resource;
- narrow and wide layouts are usable with keyboard and screen-reader semantics;
- formatting, lint, strict type checks, unit tests, and production build pass;
- no Python, API, schema, authentication, default, or Wan2.1 runtime change is required.

## Related documents

- [ADR-005: React, TypeScript, and Vite frontend](../decisions/ADR-005-react-typescript-vite-frontend.md)
- [Generation Contract v1](../contracts/generation.md)
- [HTTP API Mapping v1](http-api-v1.md)
- [Design System](../../DESIGN.md)
