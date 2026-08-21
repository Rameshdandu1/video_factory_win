# Video Generation Application

Application scaffold for a video-generation product backed by [Wan2.1](https://github.com/Wan-Video/Wan2.1).

## Status

The repository contains a complete offline vertical slice: FastAPI transport, PostgreSQL durable queue, independently executed worker, fake generation backend, and safe local MP4 delivery. It also contains an external-process Wan2.1 worker adapter pinned and tested without a GPU. GPU qualification, the frontend, and the production checkpoint choice remain outstanding.

## Intended architecture

The app calls Wan2.1 through a narrow generation-backend interface. Web/API code, job orchestration, and storage remain independent of Wan2.1 so the model runtime runs in a dedicated GPU worker process.

The adapter requires a separate operator-managed Wan2.1 checkout, Python/CUDA environment, and checkpoint directory. Application code is pinned to Wan2.1 commit `9737cba9c1c3c4d04b33fcad41c111989865d315`; it never follows a moving branch. See [Wan2.1 Runtime Specification v1](docs/specifications/wan21-runtime-v1.md) for the model pins and runtime procedure.

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

## Run the pinned Wan2.1 worker

Keep the fake backend for normal development and CI. To opt into real generation, first prepare a separate Wan2.1 checkout, matching checkpoint, and GPU Python environment as described in [Wan2.1 Runtime Specification v1](docs/specifications/wan21-runtime-v1.md). Then change `VIDEO_APP_BACKEND` to `wan21`, add all five `VIDEO_APP_WAN21_*` values shown in [.env.example](.env.example), and make the configured model capability match the selected task.

If you want to use one worker cycle to validate configuration, first confirm through the jobs API that the queue contains no queued jobs, then run:

```powershell
.\.venv\Scripts\video-app-worker.exe --env-file .env --once
```

`--once` is not a dry run. It performs recovery and one claim attempt, so it will execute one queued generation if a job is available. The adapter rejects an unpinned or dirty checkout, a mismatched model revision, unsupported capabilities, and invalid runtime paths at worker startup. The API does not load Wan2.1. Real generation still requires the explicit marked GPU smoke test before this runtime is treated as qualified.

## Next milestone

Run and record the pinned Wan2.1 GPU smoke test on the target Windows/CUDA hardware, verify cancellation cleanup, and lock the external runtime dependency set. This does not change the public API contract.
