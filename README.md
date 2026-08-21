# Video Generation Application

Application scaffold for a video-generation product backed by [Wan2.1](https://github.com/Wan-Video/Wan2.1).

## Status

The repository contains the accepted MVP contract, framework-independent generation domain, offline fake backend, application job orchestration, safe local artifact storage, quality tooling, and CI scaffold. PostgreSQL is the accepted durable job store; the frontend remains intentionally undecided until recorded in an ADR.

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

Type `\q` to leave `psql`. Stop the service without deleting its data with:

```powershell
docker compose down
```

`.env` is ignored by Git. Change its local password if this database will be reachable by anything other than your machine. The development port is bound to `127.0.0.1` only.

## Next milestone

Implement the PostgreSQL migration and durable job repository, then deliver one end-to-end text-to-video job before downloading model weights.
