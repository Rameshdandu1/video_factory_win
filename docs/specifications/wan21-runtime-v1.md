# Wan2.1 Runtime Specification v1

Status: External adapter implemented and offline-tested on 2026-08-21; GPU qualification pending

This specification defines how the worker invokes a pinned external Wan2.1 runtime without changing Generation Contract v1. It is both the operator procedure and the exact adapter boundary. It does not select a production checkpoint, add generation defaults, or claim that real GPU generation has passed.

## Scope

The runtime supports text-to-video generation only. The API process continues to validate and enqueue jobs without importing Wan2.1, loading checkpoints, or requiring CUDA. A worker configured with `VIDEO_APP_BACKEND=wan21` constructs the adapter and starts one external generation process for each claimed job.

Wan2.1 source, model weights, Python packages, CUDA libraries, caches, temporary media, and generated media remain outside the repository. The application does not copy or patch upstream source.

## Pinned upstream inputs

| Component | Upstream identifier | Required revision |
| --- | --- | --- |
| Wan2.1 code | [`Wan-Video/Wan2.1`](https://github.com/Wan-Video/Wan2.1) | [`9737cba9c1c3c4d04b33fcad41c111989865d315`](https://github.com/Wan-Video/Wan2.1/commit/9737cba9c1c3c4d04b33fcad41c111989865d315) |
| T2V-1.3B checkpoint | [`Wan-AI/Wan2.1-T2V-1.3B`](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B) | [`37ec512624d61f7aa208f7ea8140a131f93afc9a`](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B/tree/37ec512624d61f7aa208f7ea8140a131f93afc9a) |
| T2V-14B checkpoint | [`Wan-AI/Wan2.1-T2V-14B`](https://huggingface.co/Wan-AI/Wan2.1-T2V-14B) | [`a064a6c71f5be440641209c07bf2a5ce7a2ff5e4`](https://huggingface.co/Wan-AI/Wan2.1-T2V-14B/commit/a064a6c71f5be440641209c07bf2a5ce7a2ff5e4) |

The adapter verifies the Git revision of the local code checkout and requires the whole checkout to have no non-ignored modifications or untracked files. It verifies that the configured model revision matches the allowlisted revision for the selected task, but it cannot prove the provenance of arbitrary files already present in the checkpoint directory. The operator must provision that directory from the listed checkpoint revision.

The upstream code and checkpoint repositories publish Apache-2.0 licenses. Operators must still review and record the licenses of the external Python/CUDA dependency set before release.

## Supported capability matrix

| Wan2.1 task | Allowed resolutions | Allowed frame counts | Model revision |
| --- | --- | --- | --- |
| `t2v-1.3B` | `832x480`, `480x832` | `81` | `37ec512624d61f7aa208f7ea8140a131f93afc9a` |
| `t2v-14B` | `832x480`, `480x832`, `1280x720`, `720x1280` | `81` | `a064a6c71f5be440641209c07bf2a5ce7a2ff5e4` |

The configured logical model ID remains application-owned. `VIDEO_APP_MODEL_RESOLUTIONS` and `VIDEO_APP_MODEL_FRAME_COUNTS` must be a non-empty subset of the selected task row. Generation Contract v1 still accepts a signed 64-bit seed. The adapter deterministically maps a negative seed into the upstream non-negative seed range; it never asks Wan2.1 to choose a new random seed.

The adapter does not rewrite prompts and does not pass prompt-extension or sampler-tuning flags. Upstream behavior at the pinned code revision therefore supplies the sampler settings. Any application-owned default, prompt processing, or sampler change requires a specification update and evidence under `AGENTS.md`.

## Configuration reference

These values are required only when `VIDEO_APP_BACKEND=wan21`. All paths must be absolute.

| Environment variable | Meaning | Constraint |
| --- | --- | --- |
| `VIDEO_APP_WAN21_REPOSITORY_ROOT` | Local external Wan2.1 checkout | Existing clean checkout at the pinned Git revision with `generate.py` present |
| `VIDEO_APP_WAN21_CHECKPOINT_DIR` | Local checkpoint directory | Existing directory provisioned from the selected model revision |
| `VIDEO_APP_WAN21_PYTHON` | Python executable for the GPU environment | Existing executable outside the application process |
| `VIDEO_APP_WAN21_TASK` | Upstream task name | Exactly `t2v-1.3B` or `t2v-14B` |
| `VIDEO_APP_WAN21_MODEL_REVISION` | Declared checkpoint revision | Must match the selected task in the capability matrix |

Runtime settings require absolute repository, checkpoint, Python, and data-root paths. At adapter construction, the final path component of the repository root, checkpoint directory, Python executable, and generated output root must not itself be a symbolic link or Windows reparse point. The adapter does not validate every ancestor as a separate trust boundary, so the operator must own and protect the containing directories. The adapter creates server-named candidates below the application's temporary root; prompts and job IDs never determine paths.

## How to configure the worker

### Prerequisites

- Docker PostgreSQL is running and the application migrations are current.
- The Wan2.1 repository is checked out at the exact code revision above.
- One checkpoint directory contains files from its exact listed model revision.
- A separate Python environment contains the operator-selected Wan2.1, PyTorch, and CUDA dependencies.
- The target GPU has been assessed for the chosen model. This repository does not yet certify a VRAM profile.

### Steps

1. Verify the external checkout from its repository directory:

   ```powershell
   git rev-parse HEAD
   git status --short --untracked-files=all
   ```

   The first command must print `9737cba9c1c3c4d04b33fcad41c111989865d315`. The second command must print nothing. Do not point the worker at a moving branch or a checkout with non-ignored modifications or untracked files.

2. Copy `.env.example` to `.env`, set `VIDEO_APP_BACKEND=wan21`, and provide all five `VIDEO_APP_WAN21_*` values. Set the logical capability to a supported subset. For example, T2V-1.3B may use:

   ```dotenv
   VIDEO_APP_BACKEND=wan21
   VIDEO_APP_MODEL_RESOLUTIONS=832x480,480x832
   VIDEO_APP_MODEL_FRAME_COUNTS=81
   VIDEO_APP_WAN21_REPOSITORY_ROOT=C:/path/to/Wan2.1
   VIDEO_APP_WAN21_CHECKPOINT_DIR=C:/path/to/Wan2.1-T2V-1.3B
   VIDEO_APP_WAN21_PYTHON=C:/path/to/wan21-venv/Scripts/python.exe
   VIDEO_APP_WAN21_TASK=t2v-1.3B
   VIDEO_APP_WAN21_MODEL_REVISION=37ec512624d61f7aa208f7ea8140a131f93afc9a
   ```

3. To validate construction with one worker cycle, first confirm through the jobs API that the queue contains no queued jobs. Then run from the application repository:

   ```powershell
   .\.venv\Scripts\video-app-worker.exe --env-file .env --once
   ```

   `--once` is not a dry run. It performs expired-lease recovery and one claim attempt, and it will execute one queued generation if a job is available. With an empty queue, the command validates configuration, constructs the adapter, performs that one cycle, and exits. A bad path, code revision, model revision, or capability prevents the worker from claiming generation work.

4. Start the worker normally only after the preflight succeeds:

   ```powershell
   .\.venv\Scripts\video-app-worker.exe --env-file .env
   ```

## Invocation and privacy boundary

The worker invokes the configured Python executable without a shell. Fixed adapter arguments carry the task, resolution, frame count, checkpoint directory, output path, and normalized seed. The private prompt is sent through standard input to a fixed Python wrapper, so it is absent from the process argument list. After Wan2.1 returns, the same wrapper uses the external runtime's `imageio` installation to decode every frame. It exits successfully only when the decoded frame count, width, and height exactly match the normalized request.

Wan2.1 logs its parsed arguments and prompt at the pinned revision. The adapter therefore discards upstream standard output and standard error. It does not copy raw upstream diagnostics into public failures. The child receives a sanitized allowlist of required operating-system, CUDA, and cache variables. Application credentials and database settings are excluded. The adapter sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, disabling online resolution through those libraries. This is not an operating-system network sandbox and does not by itself block every possible outbound connection.

This privacy choice reduces runtime diagnostics. Operational logging may later add safe structured telemetry, but it must redact prompts, credentials, checkpoint paths, and raw backend errors.

## Completion, failure, and cancellation

The adapter writes to a server-generated temporary `.mp4` candidate. Child success confirms that the external runtime decoded the exact requested dimensions and frame count, but it is not the only acceptance check. Application-side structural validation also requires an existing, regular, non-link `.mp4` whose top-level box layout starts with `ftyp` and contains nonempty `moov` and `mdat` payloads. Malformed box sizes, missing boxes, empty payloads, and trailing partial headers fail validation. The artifact store then copies the accepted candidate to an opaque final name, computes its checksum and size, and publishes it atomically. Temporary candidates are removed after failure and cancellation.

Current adapter failures map exactly as follows:

- A request outside the configured capability becomes non-retryable `UNSUPPORTED_PARAMETERS`.
- A configured repository, checkpoint, or Python path that disappears after startup, or an operating-system error while spawning the child, becomes non-retryable `MODEL_UNAVAILABLE`.
- A nonzero child exit, imageio decode mismatch, missing output, or structurally invalid MP4 becomes retryable `GENERATION_FAILED`.
- Invalid paths, pins, tasks, or capabilities found while constructing the worker are startup configuration errors, so no job is claimed.

The adapter does not yet preflight disk space, CUDA availability, or VRAM and does not currently emit `INSUFFICIENT_RESOURCES`. A resource failure reported by an already-started child surfaces as `GENERATION_FAILED`; an operating-system error while spawning uses `MODEL_UNAVAILABLE`. All persisted backend failures use fixed safe messages. The worker never exposes the prompt, host paths, subprocess output, or raw exceptions. A retry remains an explicit new job.

The adapter polls the application cancellation probe while the child runs and starts the subprocess in a platform-specific process group:

- On POSIX, `start_new_session=True` creates a new session and process group. Cleanup signals that group with `SIGTERM`, waits for the bounded grace period, then uses `SIGKILL` and another bounded wait if it remains active.
- On Windows, `CREATE_NEW_PROCESS_GROUP` creates a new process group. Cleanup invokes the system `taskkill.exe` with `/PID`, `/T`, and `/F` for the active process tree and bounds both the command and subsequent process wait. If tree signaling is unavailable or fails, cleanup falls back to the direct child termination primitives.

After the process stops, cleanup awaits or cancels the communication task within a bounded interval and removes the candidate before confirming cancellation. These controls handle cancellation and worker-observed failures; they do not guarantee orphan-free cleanup if the worker parent exits unexpectedly before running its cleanup path. Real Windows/CUDA process-tree cancellation remains part of the GPU qualification gate.

Wan2.1 does not provide a reliable progress protocol through this subprocess boundary. The adapter emits no progress reports. PostgreSQL lease heartbeats continue independently, and the public `progress` field remains null while generation runs.

## GPU qualification gate

Normal unit, architecture, and integration tests do not import Wan2.1, download weights, or require CUDA. The marked smoke test is opt-in and must run with the exact external checkout and checkpoint before this runtime is considered qualified:

```powershell
$env:VIDEO_APP_RUN_WAN21_GPU_TESTS = "1"
$env:VIDEO_APP_WAN21_REPOSITORY_ROOT = "C:/path/to/Wan2.1"
$env:VIDEO_APP_WAN21_CHECKPOINT_DIR = "C:/path/to/Wan2.1-T2V-1.3B"
$env:VIDEO_APP_WAN21_PYTHON = "C:/path/to/wan21-venv/Scripts/python.exe"
$env:VIDEO_APP_WAN21_TASK = "t2v-1.3B"
.\.venv\Scripts\python.exe -m pytest -m gpu tests/gpu/backends/test_wan21_smoke.py
```

Qualification must record the Python, PyTorch, CUDA, driver, GPU, VRAM, external dependency lock, selected task/checkpoint, generation duration, semantic decode and structural output validation, and process-tree cancellation cleanup result. Until that record exists, the adapter is implemented but not production-ready.

## Related contracts

- [Generation Contract v1](../contracts/generation.md)
- [MVP Requirements v1](../mvp-requirements.md)
- [Application boundaries](../architecture.md)
- [ADR-001: Application boundaries](../decisions/ADR-001-application-boundaries.md)
- [Local artifact storage](../decisions/ADR-004-local-artifact-storage.md)
