# Video Generation Application

Application scaffold for a video-generation product backed by [Wan2.1](https://github.com/Wan-Video/Wan2.1).

## Status

The repository currently contains the engineering rules and initial project boundary. The application stack and first vertical slice are intentionally not selected yet.

## Intended architecture

The app will call Wan2.1 through a narrow generation-backend interface. Web/API code, job orchestration, and storage should remain independent of Wan2.1 so the model runtime can run in a dedicated GPU process or worker.

Wan2.1 currently requires Python 3.10+, PyTorch 2.4+, and model-specific checkpoints. Record an exact upstream commit when integration begins; do not rely on a moving branch.

## Repository policy

See [AGENTS.md](AGENTS.md) for coding, testing, GPU-job, media-safety, and Git rules.

## Next milestone

Choose the API/UI stack, add a fake generation backend, and implement one end-to-end text-to-video job before downloading model weights.

