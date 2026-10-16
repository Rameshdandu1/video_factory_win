# ADR-016: RunPod ephemeral deployment and private access

Status: Accepted  
Date: 2026-10-16

## Context

The application already has separate FastAPI and worker processes, a PostgreSQL durable queue,
local artifact storage, and a built React client. Manual RunPod setup left those processes attached
to interactive Jupyter terminals and made recovery after a Pod filesystem replacement ambiguous.
The current deployment target is an Ubuntu-based RunPod GPU Pod with ephemeral container storage.
No paid persistent volume, external database, public endpoint, or Docker-in-Docker service is
authorized.

## Decision

Add replaceable deployment tooling outside `src/video_app/`:

- Supervisor owns exactly one API, worker, Nginx, local PostgreSQL, and userspace `tailscaled`
  process through a private Unix control socket.
- Nginx serves only `frontend/dist`, proxies the existing relative `/api/` routes, and binds to
  `127.0.0.1:5173`; FastAPI and PostgreSQL also bind only to loopback.
- Tailscale Serve is the private HTTPS entry point. Funnel and a public listener are excluded.
- Releases are immutable full-SHA checkouts below `/opt/video-factory/releases`; `current` is an
  atomic symlink. Ordinary start never changes source.
- Deployment configuration remains in the application's literal `KEY=VALUE` format and is
  validated with the canonical runtime parser. Supervisor and shell do not source it.
- PostgreSQL data, application media, Tailscale identity, logs, and configuration live outside
  release directories. Backups include a PostgreSQL dump and application media, but exclude
  credentials and Tailscale identity.
- The initial deployment is explicitly fake-backend demo mode. Existing GPU runtime qualification
  gates remain authoritative and separate.
- Pod-local storage and Pod-local backups are always labelled ephemeral. This tooling does not
  claim or create persistence.

The deployment manager uses only the Python standard library so it can run before the application
environment exists. Shell files are thin Ubuntu bootstrap/package entry points.

## Consequences

- Closing an interactive terminal no longer stops manually launched detached services; Supervisor
  owns and restarts them with bounded retry behavior.
- A process crash and a destroyed container are distinct. A destroyed container requires the
  versioned GitHub bootstrap and, for data recovery, a previously exported verified backup.
- Automatic Pod boot integration is `NOT_CONFIGURED` until an operator inspects a specific
  template's startup contract. The deployment never overwrites `/start_script.sh`, ComfyUI, or
  Jupyter startup.
- Schema updates remain forward-only. A pre-update backup is created, and switching the code symlink
  back is not represented as reversing a migration.
- Tailscale userspace networking can configure Serve but cannot prove external browser DNS/TCP/TLS
  from inside the same Pod. Status reports that evidence as not verified.

## Rejected alternatives

- Systemd inside the application container: not reliably available in RunPod templates.
- Vite preview as production serving: it is not the selected production web server.
- Docker Compose or Docker-in-Docker: unnecessary and incompatible with the immediate target.
- Public ingress or Tailscale Funnel: violates the private-access requirement.
- Embedding credentials, database contents, model weights, or a Tailscale identity in an image:
  unsafe and not a recovery strategy.
- Replacing an unknown template entrypoint: risks breaking ComfyUI/Jupyter and losing temporary
  storage.
