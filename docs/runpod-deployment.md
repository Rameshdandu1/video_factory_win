# RunPod deployment and recovery

Status: implemented for an Ubuntu x86_64 RunPod GPU Pod; real RunPod/Tailscale execution still
requires operator verification.

This guide deploys the CPU-only fake-backend demo. It does not download model weights, qualify a
GPU runtime, make a 15-minute film, provision paid storage, or make temporary container storage
persistent. All paths below remain inside the Pod unless you explicitly download a backup.

## What the deployment owns

`runpodctl` owns only these Supervisor programs:

- `video-factory-postgres` on `127.0.0.1:5432`;
- `video-factory-api` on `127.0.0.1:8000`;
- `video-factory-worker` (exactly one process);
- `video-factory-nginx` on `127.0.0.1:5173`;
- `video-factory-tailscaled` in userspace-networking mode.

It never calls `pkill`, `killall`, Docker, systemd, or RunPod control-plane APIs. It does not stop,
edit, or adopt ComfyUI, JupyterLab, or unrelated listeners. An unrelated owner of a required port is
a hard conflict.

The filesystem layout is:

| Purpose | Path |
| --- | --- |
| Immutable full-SHA releases | `/opt/video-factory/releases/` |
| Active release symlink | `/opt/video-factory/current` |
| Private application config | `/etc/video-factory/video-factory.env` |
| PostgreSQL, media, metadata, Tailscale state | `/var/lib/video-factory/` |
| Rotated service logs | `/var/log/video-factory/` |
| Private sockets and locks | `/run/video-factory/` |

Source releases never contain uploads, generated media, PostgreSQL data, caches, model weights, or
Tailscale identity.

## Fresh installation

The bootstrap and installer require a full approved Git SHA. They refuse a branch name or moving
tag. Resolve the proposed `main` revision, compare it with the reviewed GitHub commit, and type that
same SHA at the approval prompt.

**RUNPOD TERMINAL (root, fresh Ubuntu-based ComfyUI Pod):**

```bash
set -e
VIDEO_FACTORY_REF="$(git ls-remote https://github.com/Rameshdandu1/video_factory_win.git refs/heads/main | awk 'NR == 1 {print $1}')"
printf 'Proposed revision: %s\n' "${VIDEO_FACTORY_REF}"
read -r -p 'Type the approved full revision to continue: ' APPROVED_REF
test "${APPROVED_REF}" = "${VIDEO_FACTORY_REF}"
curl --fail --silent --show-error --location \
  "https://raw.githubusercontent.com/Rameshdandu1/video_factory_win/${VIDEO_FACTORY_REF}/scripts/runpod-bootstrap.sh" \
  --output /tmp/video-factory-bootstrap.sh
bash /tmp/video-factory-bootstrap.sh \
  --ref "${VIDEO_FACTORY_REF}" \
  --accept-ephemeral \
  --initialize-empty-database
```

The command installs only missing Ubuntu packages, verifies the pinned NodeSource signing-key
fingerprint if Node 22 must be installed, uses the official signed Tailscale apt source, creates a
dedicated application virtual environment, runs `npm ci`, type-checks/builds the frontend, records
package/build metadata, initializes an explicitly empty PostgreSQL data directory, derives and
applies the checkout's current Alembic heads, then starts detached Supervisor services.

Rerunning the same approved ref validates and reuses the existing configuration, credentials,
database, media, release build, and Tailscale identity. A different ref requires `update`.
If an authorized first installation was interrupted, its manifest remains `initializing`; rerunning
the same command resumes with the preserved secret and data instead of calling `initdb` again.

Fresh installation intentionally creates `VIDEO_APP_BACKEND=fake`. Real Wan2.1 or another runtime
still requires the repository's separate adapter-specific GPU qualification evidence. Do not edit
the managed environment to bypass those checks.

## Everyday operations

**RUNPOD TERMINAL:**

```bash
runpodctl start
runpodctl status
runpodctl logs --lines 200
runpodctl doctor
runpodctl restart
runpodctl stop
```

Use one service's log without printing configuration:

**RUNPOD TERMINAL:**

```bash
runpodctl logs --service worker --lines 300
runpodctl logs --service api --lines 300
runpodctl logs --service tailscale --lines 300
```

Machine-readable inspection is read-only:

**RUNPOD TERMINAL:**

```bash
runpodctl status --json
runpodctl doctor --json
```

`status` distinguishes process state, database authentication, schema revision, local HTTP transport
reachability and application health, the `/api` reverse proxy, fake/GPU backend state, Tailscale
authorization/Serve state, storage, backup evidence, and Pod-level boot integration. Frontend and
API probes require HTTP 200 plus the expected application HTML or exact health JSON; an HTTP error
response is transport-reachable but unhealthy. `doctor` does not repair or reconfigure anything.

Stable command exit codes are `0` success, `3` invalid/missing configuration, `4` ownership or
state conflict, `5` missing/unsupported dependency, `6` service/readiness failure, `7` backup or
restore failure, `8` private-network failure, and `130` operator interruption.

Run the explicit end-to-end fake job only when an extra persistent test record is acceptable:

**RUNPOD TERMINAL:**

```bash
runpodctl smoke-test --deadline-seconds 60
```

The command first proves that the selected backend is `fake`, submits the real Generation Contract
v1 payload, waits for the worker, checks the terminal job, and validates the MP4 container response.
It reports `real_ai_video_generated: false`. Routine checks never claim a job or invoke paid/GPU
inference.

## Private Tailscale access

The daemon uses `--tun=userspace-networking`, a persistent Pod-local state directory, and a private
socket. Its identity survives service restarts while this filesystem exists. Do not copy that state
to a simultaneously running Pod.

Interactive authorization is preferred because an auth key never enters shell history:

**RUNPOD TERMINAL:**

```bash
runpodctl tailscale-login
runpodctl status
```

Complete the one-time approval shown by the dedicated login command. General status and support
output intentionally omit login URLs and keys. Once authorized, `runpodctl` configures private
Tailscale Serve HTTPS to Nginx and prints the actual current node URL. It never enables Funnel.

For explicitly authorized unattended setup, provision a private auth-key file out of band with mode
`0600`, then use its absolute path. Do not type the key as an argument or save it in the repository:

**RUNPOD TERMINAL:**

```bash
chmod 0600 /run/secrets/video-factory-tailscale-auth-key
runpodctl tailscale-login --auth-key-file /run/secrets/video-factory-tailscale-auth-key
```

The daemon reads that file through its private config; after successful authorization the reference
is removed and the persisted node state is reused. Delete the source key according to its secret
delivery policy.

Tailscale userspace networking cannot provide meaningful proof of external DNS/TCP/TLS from inside
the same Pod. Status therefore labels external TLS as not verified. Test from a second authorized
Windows device using the actual URL printed by `runpodctl status`. If Tailscale is not installed or
authorized on Windows, install it and complete its account login first:

**WINDOWS POWERSHELL:**

```powershell
winget install --exact --id Tailscale.Tailscale
& "$env:ProgramFiles\Tailscale\tailscale.exe" up
```

Then run the external checks:

**WINDOWS POWERSHELL:**

```powershell
& "$env:ProgramFiles\Tailscale\tailscale.exe" status
$VideoFactoryUrl = Read-Host "Paste the exact https URL printed by runpodctl status"
Invoke-WebRequest -Uri $VideoFactoryUrl -Method Head
Invoke-RestMethod -Uri "$($VideoFactoryUrl.TrimEnd('/'))/api/v1/health"
```

Interpret failures separately: `doctor` identifies daemon and authorization/Serve state; Windows
then supplies peer-online, MagicDNS, TCP 443, certificate/TLS, and backend HTTP evidence. A TCP
connection alone is not an HTTPS test.

### Optional Vite development access

Production never runs Vite. If an operator deliberately runs the development server behind
Tailscale Serve, derive the exact current DNS name from the node state and pass only that hostname.
The Vite config rejects non-`ts.net` input, never enables `allowedHosts: true`, and keeps the `/api`
proxy.

**RUNPOD TERMINAL (development only, not managed production):**

```bash
export VIDEO_FACTORY_DEV_HOSTNAME="$(tailscale --socket /run/video-factory/tailscaled.sock status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
cd /opt/video-factory/current/frontend
npm run dev
```

## Updating an approved revision

An update prepares and builds the candidate before stopping application services, creates a
consistent pre-migration database/media backup, stops only owned services, applies the candidate's
derived Alembic heads with the managed database URL, atomically switches `current`, and restarts.
In fake mode it also runs the end-to-end smoke test.

Resolve and approve the new full SHA as in fresh installation, then:

**RUNPOD TERMINAL:**

```bash
read -r -p 'Paste the approved 40-character update revision: ' APPROVED_UPDATE_REF
case "${APPROVED_UPDATE_REF}" in
  (????????????????????????????????????????) ;;
  (*) printf 'A full 40-character revision is required.\n' >&2; exit 3 ;;
esac
runpodctl update --ref "${APPROVED_UPDATE_REF}"
```

The manager also validates lowercase hexadecimal content. It refuses dirty or wrong-origin release
checkouts. A code symlink rollback is not a database migration rollback; retain the printed
pre-update archive until the update is accepted.

## Backup and off-Pod export

Backups briefly stop the owned API and worker so the PostgreSQL dump and media tree form one
recoverable set. Nginx may remain available, but writes are paused. The archive contains:

- a custom-format PostgreSQL dump without ownership or credentials;
- uploads/generated artifacts under the configured application data root;
- deployed revision, PostgreSQL major, migration heads, sampled core-table counts, a sample-media
  path, and SHA-256 checksums for every included artifact.

It excludes the virtualenv, `node_modules`, source, caches, model weights, logs, configuration,
database password, cursor secret, and Tailscale identity.

Create a local archive in the template's Jupyter-visible workspace:

**RUNPOD TERMINAL:**

```bash
BACKUP_PATH="/workspace/video-factory-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
runpodctl backup --output "${BACKUP_PATH}"
printf 'LOCAL ONLY — NOT PROTECTED FROM CONTAINER LOSS: %s\n' "${BACKUP_PATH}"
sha256sum "${BACKUP_PATH}"
```

Download that exact file immediately through the existing authenticated RunPod Jupyter file browser.
This application does not create public download endpoints or provision paid storage. After the
download, verify the printed digest:

**WINDOWS POWERSHELL:**

```powershell
$BackupPath = Read-Host "Enter the downloaded backup's full Windows path"
Get-FileHash -Algorithm SHA256 -LiteralPath $BackupPath
```

`runpodctl status` continues to say off-Pod backup `NOT_VERIFIED`; the Pod cannot prove a browser
download or the durability of the Windows destination.

## Restore

Prefer a fresh installation and upload the archive to a Jupyter-visible path first. The installer
creates a new credential and empty application database, verifies the archive/checksums/PostgreSQL
major, restores into a temporary database, validates current migration heads, then atomically swaps
the active names with guarded rollback for database and media. It never executes files from the archive and rejects traversal, links, special
files, and checksum mismatches.

**RUNPOD TERMINAL (fresh container after uploading the archive):**

```bash
set -e
VIDEO_FACTORY_REF="$(git ls-remote https://github.com/Rameshdandu1/video_factory_win.git refs/heads/main | awk 'NR == 1 {print $1}')"
printf 'Proposed revision: %s\n' "${VIDEO_FACTORY_REF}"
read -r -p 'Type the approved full revision to continue: ' APPROVED_REF
test "${APPROVED_REF}" = "${VIDEO_FACTORY_REF}"
read -r -p 'Enter the absolute uploaded backup path: ' RESTORE_ARCHIVE
test -f "${RESTORE_ARCHIVE}"
curl --fail --silent --show-error --location \
  "https://raw.githubusercontent.com/Rameshdandu1/video_factory_win/${VIDEO_FACTORY_REF}/scripts/runpod-bootstrap.sh" \
  --output /tmp/video-factory-bootstrap.sh
bash /tmp/video-factory-bootstrap.sh \
  --ref "${VIDEO_FACTORY_REF}" \
  --accept-ephemeral \
  --restore "${RESTORE_ARCHIVE}"
```

Replacing a populated installation is deliberately a separate action:

**RUNPOD TERMINAL:**

```bash
INSTALLATION_ID="$(runpodctl status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["installation_id"])')"
read -r -p 'Enter the absolute backup path that will replace existing records: ' RESTORE_ARCHIVE
runpodctl restore \
  --archive "${RESTORE_ARCHIVE}" \
  --replace-existing \
  --confirm "RESTORE-${INSTALLATION_ID}"
```

The old database and media remain available during validation and are retired only after the
restored deployment passes startup checks. If no off-Pod backup exists after a filesystem loss,
records and media cannot be recovered; use the fresh empty installation flow and acknowledge that
outcome.

## Database credential rotation

Rotation updates the PostgreSQL role and the atomic application configuration together, validates
the new authenticated connection, and rolls both back on failure. The password is never printed.

**RUNPOD TERMINAL:**

```bash
umask 077
read -r -s -p 'New database password: ' NEW_DATABASE_PASSWORD
printf '\n'
printf '%s' "${NEW_DATABASE_PASSWORD}" >/run/video-factory-new-db-password
unset NEW_DATABASE_PASSWORD
runpodctl rotate-db-password --password-file /run/video-factory-new-db-password
rm -f /run/video-factory-new-db-password
```

Running `runpodctl rotate-db-password` without `--password-file` generates a cryptographically random
password and stores it without displaying it.

## Crash recovery versus filesystem loss

### Process crash, filesystem intact

Supervisor uses one process per service, bounded start retries, process-group termination, and
rotated logs. `autorestart=unexpected` restarts a crashed worker without starting an additional
worker. The worker continues to use the application's existing lease/recovery semantics; deployment
code does not requeue expensive jobs.

**RUNPOD TERMINAL:**

```bash
runpodctl status
runpodctl restart
runpodctl smoke-test --deadline-seconds 60
```

### Container filesystem replaced

The installer, `/usr/local/bin/runpodctl`, database, media, and a local-only backup can all be gone.
Run the versioned GitHub bootstrap again and choose exactly one outcome:

- `--restore ABSOLUTE_ARCHIVE` after uploading a verified off-Pod archive; or
- `--initialize-empty-database` to explicitly accept a new empty deployment.

The bootstrap pins and records one full revision; it does not follow a branch on every restart.
Tailscale may issue a different identity and URL on a fresh container. Never expect the previous URL
to survive without its state directory.

## Pod-level boot integration

Current status: **NOT CONFIGURED / NOT TESTED**.

Detached Supervisor handles terminal closure and process crashes only while the container remains
running. It does not prove startup after RunPod replaces or restarts a container. RunPod templates
vary, and this implementation has not inspected the active template's entrypoint chain. Therefore it
does not overwrite `/start_script.sh`, `ENTRYPOINT`, `CMD`, or any ComfyUI/Jupyter hook.

Before configuring a template hook, an operator must inspect the exact image/template startup
behavior and prove that a composable hook preserves ComfyUI and Jupyter. Changing Pod configuration
can reset temporary storage. Until that evidence exists, use the versioned bootstrap manually after
a replacement and `runpodctl start` after an intact-filesystem restart. `runpodctl foreground` is
available only for a verified container-entrypoint integration; it stops owned services on TERM/INT
and must not be inserted into an unknown template blindly.

## Evidence and remaining operator actions

| Check | Where | Delivery status |
| --- | --- | --- |
| Python unit, architecture, lint, format, and strict typing | LOCAL/CI BUILD MACHINE | Automated |
| Frontend format, lint, type check, tests, production build | LOCAL/CI BUILD MACHINE | Automated |
| Bash parsing and ShellCheck | LOCAL/CI BUILD MACHINE | Automated |
| Config parsing, special-character passwords, repeat start/install, port conflicts, archive safety, static isolation | LOCAL/CI BUILD MACHINE | Automated |
| PostgreSQL migration integration | CI PostgreSQL service | Existing automated job |
| Installer PostgreSQL ownership, parent traversal, socket, authentication, migrations, repeat install | Disposable root-owned Ubuntu CI filesystem with real non-root `postgres` account | Automated |
| Clean Ubuntu package installation and Supervisor process recovery | Disposable RUNPOD TERMINAL | Operator must execute |
| Tailscale login, approval, Serve certificate, actual private URL | RUNPOD TERMINAL | Operator must execute |
| Peer/MagicDNS/TCP/TLS/browser verification | WINDOWS POWERSHELL | Operator must execute |
| Off-Pod backup transfer and digest comparison | WINDOWS POWERSHELL | Operator must execute |
| Template boot hook compatibility | Specific RunPod template | NOT CONFIGURED / NOT TESTED |
| Wan2.1/Wan2.2/VACE/Animate/FFmpeg qualification | Authorized GPU environment | Separate explicit workflows |

Deployment success is evidence for the fake demo only. It is not evidence for CUDA compatibility,
VRAM capacity, emotional acting, Telugu TTS or pronunciation, lip-sync, final sound, real-media
acceptance, or a 900-second film.

## Upstream operational references

- [Tailscale userspace networking](https://tailscale.com/docs/concepts/userspace-networking)
- [`tailscaled` state and socket options](https://tailscale.com/docs/reference/tailscaled)
- [Tailscale daemon configuration file](https://tailscale.com/kb/1654/tailscaled-config-file)
- [Tailscale Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Supervisor process configuration](https://docs.supervisord.org/configuration.html)
