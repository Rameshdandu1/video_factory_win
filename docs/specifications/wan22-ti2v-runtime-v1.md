# Wan2.2 TI2V runtime v1

Status: Accepted

## Exact pins

- Code: `Wan-Video/Wan2.2@1ea34ff48f87168174e12956e200b1d908b1c5ff`
- Model: `Wan-AI/Wan2.2-TI2V-5B@921dbaf3f1674a56f47e83fb80a34bac8a8f203e`
- Task: `ti2v-5B`
- Area presets: `1280x704` and `704x1280`
- Frames: `81`

The adapter invokes the pinned repository as an external subprocess. It does not import Wan2.2 into
the API or copy upstream source into first-party packages. The command enables model offload, model
dtype conversion, and T5 CPU placement and always includes `--image`.

## Qualification gate

The runtime is enabled only when an operator-provided JSON qualification report is an existing
absolute file, is marked `approved`, repeats the exact code/model/task pins, records a checkpoint
manifest SHA-256 matching configuration, and records positive minimum free disk and VRAM values.
The worker independently checks the clean Git revision, executable/checkpoint paths, CUDA visibility,
free VRAM, and free disk before accepting work.

Qualification requires opt-in real-GPU evidence that input A and input B produce distinct recorded
conditioning hashes, cancellation cleans subprocesses and temporary derivatives, output media probes
successfully, and no T2V fallback occurred. CPU tests validate argument plumbing but do not qualify a
machine or checkpoint.
