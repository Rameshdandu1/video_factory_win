# Video Generation Application

Application scaffold for a video-generation product backed by [Wan2.1](https://github.com/Wan-Video/Wan2.1).

## Status

The repository contains the engineering constitution, enforceable architecture boundaries, draft generation contract, quality tooling, and CI scaffold. Infrastructure and UI framework choices remain intentionally undecided until recorded in ADRs.

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

## Next milestone

Select the API/queue/storage stack through ADRs, implement the accepted Generation Contract v1 with a fake backend, and deliver one end-to-end text-to-video job before downloading model weights.
