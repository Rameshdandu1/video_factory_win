# Video Generation Application

Application scaffold for a video-generation product backed by [Wan2.1](https://github.com/Wan-Video/Wan2.1).

## Status

The repository contains a complete offline quick-clip vertical slice: React browser client, FastAPI transport, PostgreSQL durable queue, independently executed worker, fake generation backend, and safe local MP4 delivery. Its additive project workflow includes owner-scoped projects, secure assets, measured media metadata, immutable timelines/captions, and the planning and approval contract for a 900-second Telugu short film. It also includes an owner-scoped Film Library, immutable project/shot reference pins, a server-rendered starting-frame composer, bounded approved reference-video guidance, and isolated Wan2.2 TI2V, VACE, and Wan Animate adapters with exact provenance and constraint-conflict rejection. All three reference-driven runtimes remain disabled until target-GPU qualification. A separately gated FFmpeg worker can render an immutable 900-second rough cut from approved storyboards and recorded Telugu dialogue; final rendering, Telugu TTS, lip-sync, and real-media acceptance remain later work. The external-process Wan2.1 worker adapter is also pinned and tested without a GPU; its target-GPU qualification remains outstanding.

## Intended architecture

The app calls Wan2.1, VACE, and Wan2.2 through one narrow generation-backend interface. Web/API code, job orchestration, and storage remain independent of model internals so each runtime runs in a dedicated GPU worker process.

The adapter requires a separate operator-managed Wan2.1 checkout, Python/CUDA environment, and checkpoint directory. Application code is pinned to Wan2.1 commit `9737cba9c1c3c4d04b33fcad41c111989865d315`; it never follows a moving branch. See [Wan2.1 Runtime Specification v1](docs/specifications/wan21-runtime-v1.md) for the model pins and runtime procedure.

The browser client is a separate top-level `frontend/` workspace selected in [ADR-005](docs/decisions/ADR-005-react-typescript-vite-frontend.md). It uses React, strict TypeScript, Vite, a typed native-fetch client, bounded polling, and plain CSS. It consumes the existing `/api/v1` contract without importing Python code or changing authentication, CORS, schemas, generation defaults, or runtime behavior. See [Frontend UI Specification v1](docs/specifications/frontend-ui-v1.md) and [DESIGN.md](DESIGN.md).

## Repository policy

Start with [AGENTS.md](AGENTS.md), then read [docs/architecture.md](docs/architecture.md), relevant contracts, and accepted decisions before modifying code.

## Local quality checks

```bash
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest -m "not gpu"
```

Frontend checks run independently from `frontend/` with Node 22.12 or newer:

```powershell
npm ci
npm run format
npm run lint
npm run typecheck
npm test
npm run build
```

## Local PostgreSQL

Docker Desktop must be running. From this repository in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
docker compose ps
```

Wait until the service reports `healthy`, then open PostgreSQL with:

```powershell
docker compose exec postgres psql -U video_app -d video_factory
```

Apply forward-only schema migrations from PowerShell:

```powershell
$env:DATABASE_URL = (Get-Content .env | Where-Object { $_ -like 'DATABASE_URL=*' }).Split('=', 2)[1]
.\.venv\Scripts\alembic.exe upgrade head
```

The current head includes additive project, asset, timeline, Telugu-film, reusable-library,
Film Bible, starting-frame composition, I2V/controlled/rough-cut/final-timeline job manifests, and
reference-guidance migrations through `20261013_0014`. Back up and inventory a
deployed database before applying it. The application does not run migrations automatically.

Run the PostgreSQL integration tests while `DATABASE_URL` remains set:

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration
```

Type `\q` to leave `psql`. Stop the service without deleting its data with:

```powershell
docker compose down
```

`.env` is ignored by Git. Change its local password if this database will be reachable by anything other than your machine. The development port is bound to `127.0.0.1` only.

## Run the offline application

The `.env` runtime values select an explicit fake model capability and an absolute data root outside the repository. Reinstall the editable package after pulling command changes:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Start the API in one PowerShell window:

```powershell
.\.venv\Scripts\video-app-api.exe --env-file .env
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive API documentation. Start the independent single-concurrency worker in a second PowerShell window:

```powershell
.\.venv\Scripts\video-app-worker.exe --env-file .env
```

The API only validates, persists, lists, cancels, and serves jobs. Generation is never run in the API process. Stop either process with `Ctrl+C`.

Start the separate frontend in a third PowerShell window:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite forwards relative `/api` requests to the local FastAPI server at `127.0.0.1:8000`; this development proxy does not enable or require backend CORS.

## Run the pinned Wan2.1 worker

Keep the fake backend for normal development and CI. To opt into real generation, first prepare a separate Wan2.1 checkout, matching checkpoint, and GPU Python environment as described in [Wan2.1 Runtime Specification v1](docs/specifications/wan21-runtime-v1.md). Then change `VIDEO_APP_BACKEND` to `wan21`, add all five `VIDEO_APP_WAN21_*` values shown in [.env.example](.env.example), and make the configured model capability match the selected task.

If you want to use one worker cycle to validate configuration, first confirm through the jobs API that the queue contains no queued jobs, then run:

```powershell
.\.venv\Scripts\video-app-worker.exe --env-file .env --once
```

`--once` is not a dry run. It performs recovery and one claim attempt, so it will execute one queued generation if a job is available. The adapter rejects an unpinned or dirty checkout, a mismatched model revision, unsupported capabilities, and invalid runtime paths at worker startup. The API does not load Wan2.1. Real generation still requires a passing report from the explicit marked GPU qualification harness before this runtime is treated as qualified.

## Qualify and run the pinned Wan2.2 TI2V worker

Keep `VIDEO_APP_WAN22_TI2V_ENABLED=false` (or omit it) until the target GPU, clean external checkout,
and exact TI2V-5B checkpoint are ready. Configure the `VIDEO_APP_WAN22_*` qualification variables
documented in [Wan2.2 TI2V Runtime v1](docs/specifications/wan22-ti2v-runtime-v1.md), including two
authorized and materially distinct starting images, then run only the explicit harness:

```powershell
$env:VIDEO_APP_RUN_WAN22_GPU_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/gpu/backends/test_wan22_ti2v_smoke.py -m gpu -q
```

After reviewing the generated report, configure its absolute path and matching checkpoint-manifest
SHA in the API environment so the composer exposes the provider. Run a separate worker environment
with `VIDEO_APP_BACKEND=wan22`. The adapter accepts only approved-image jobs pinned to its exact
backend revision; missing or changed images fail instead of falling back to text-to-video. Keep the
Wan2.1 worker running separately for `/api/v1` quick jobs.

## Qualify VACE and Wan Animate

Keep both controlled providers disabled until the external checkout, checkpoint tree, approved test
image/video, and verified FFmpeg build are ready. Configure the matching keys from `.env.example`,
then run the explicit GPU harness once for each provider:

```powershell
$env:VIDEO_APP_RUN_CONTROLLED_GPU_TESTS = "1"
$env:VIDEO_APP_CONTROLLED_QUALIFICATION_PROVIDER = "vace" # repeat with "animate"
.\.venv\Scripts\python.exe -m pytest tests/gpu/backends/test_controlled_video_smoke.py -m gpu -q
```

Review the emitted provider-specific JSON before using it as the qualification report. Run VACE and
Animate in separate worker environments by selecting `VIDEO_APP_BACKEND=vace` or
`VIDEO_APP_BACKEND=wan22-animate`; the API may list both but each worker claims only its exact pinned
jobs. These runs can consume substantial GPU time and are never part of the normal test suite.

## Qualify the FFmpeg rough-cut worker

Keep rough-cut rendering disabled until the exact FFmpeg/ffprobe build and authorized local
storyboard/dialogue fixtures are configured with the keys in `.env.example`. Then run:

```powershell
$env:VIDEO_APP_RUN_ROUGH_CUT_QUALIFICATION = "1"
.\.venv\Scripts\python.exe -m pytest tests/integration/backends/test_rough_cut_qualification.py -m integration -q
```

The harness writes `rough-cut-qualification.json` only after a real image-plus-audio export,
measured output validation, changed-input hash rejection, and cancellation cleanup pass. Review the
report, point `VIDEO_APP_ROUGH_CUT_QUALIFICATION_REPORT` at it, and use
`VIDEO_APP_BACKEND=ffmpeg-rough-cut` only in the dedicated rough-cut worker environment.

## Qualify the FFmpeg final-timeline worker

Configure the exact FFmpeg, ffprobe, and Telugu-capable font pins plus a full-duration authorized
audio fixture using `.env.example`. Run the explicit harness:

```powershell
$env:VIDEO_APP_RUN_TIMELINE_RENDER_QUALIFICATION = "1"
.\.venv\Scripts\python.exe -m pytest tests/integration/backends/test_timeline_render_qualification.py -m integration -q
```

The harness verifies a real title/caption/audio export, measured output, changed-input rejection,
and cancellation cleanup, then retains `timeline-render-review.mp4` and a report with status
`pending_operator_review`. Inspect the Telugu glyphs, title/caption presentation, and audio mix.
Only after that review may an operator set the corresponding evidence fields and status to
`approved`, configure `VIDEO_APP_TIMELINE_RENDER_QUALIFICATION_REPORT`, and start a dedicated worker
with `VIDEO_APP_BACKEND=ffmpeg-timeline-render`. This runtime never treats duration alone as film
acceptance.

## Next milestone

Qualify the pinned rough-cut and final-timeline FFmpeg workers with authorized fixtures, then
execute and retain the Wan2.2 TI2V, VACE, and Wan Animate reports on the authorized target GPU.
Configuration keys are documented in `.env.example`; media requirements are defined in
[Media Runtime v1](docs/specifications/media-runtime-v1.md). Keep each worker in its own runtime
environment. The existing Wan2.1 T2V path and v1 API remain unchanged.
