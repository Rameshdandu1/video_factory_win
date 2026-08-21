# Video Generation Application

Application scaffold for a video-generation product backed by [Wan2.1](https://github.com/Wan-Video/Wan2.1).

## Status

The repository contains a complete offline vertical slice: FastAPI transport, PostgreSQL durable queue, independently executed worker, fake generation backend, and safe local MP4 delivery. The frontend and production Wan2.1 model configuration remain intentionally undecided until recorded in ADRs.

## Intended architecture

The app will call Wan2.1 through a narrow generation-backend interface. Web/API code, job orchestration, and storage should remain independent of Wan2.1 so the model runtime can run in a dedicated GPU process or worker.

Wan2.1 currently requires Python 3.10+, PyTorch 2.4+, and model-specific checkpoints. Record an exact upstream commit when integration begins; do not rely on a moving branch.

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

## Next milestone

Pin a tested Wan2.1 revision and implement its isolated worker adapter without changing the API contract.
