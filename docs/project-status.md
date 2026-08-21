# Project Status

## Completed

- [x] Engineering constitution
- [x] Baseline architecture and dependency direction
- [x] Wan2.1 adapter boundary decision
- [x] MVP Requirements v1 accepted
- [x] Generation Contract v1 accepted
- [x] FastAPI transport framework selected through ADR-002
- [x] PostgreSQL job store and durable queue selected through ADR-003
- [x] Local MVP artifact storage selected through ADR-004
- [x] Job Persistence Specification v1 accepted
- [x] Framework-independent domain types and backend protocol
- [x] Offline fake generation backend
- [x] Application job use cases and leased worker orchestration
- [x] Safe local artifact-storage adapter
- [x] Docker Compose PostgreSQL development service
- [x] PostgreSQL schema migration and durable job repository
- [x] FastAPI-to-worker offline text-to-video vertical slice
- [x] Wan2.1 code and supported model revisions pinned
- [x] External-process Wan2.1 worker adapter implemented and covered by offline tests
- [x] Fail-closed, evidence-producing Wan2.1 GPU qualification harness implemented
- [x] Static-analysis, architecture-test, and CI scaffolding

## Next

- [ ] Run and retain the marked Wan2.1 GPU qualification report on target Windows/CUDA hardware
- [ ] Verify subprocess and temporary-file cleanup during real GPU cancellation
- [ ] Lock and record the operator-managed Wan2.1 runtime dependency set after qualification

## Explicitly undecided

- Frontend framework
- Authentication and deployment platform
- Production model/checkpoint selection
- Production GPU resource profile and sampler tuning
