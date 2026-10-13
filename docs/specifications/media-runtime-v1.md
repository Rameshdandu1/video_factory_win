# Media Runtime v1

Status: Inspection, rough-cut, and final-timeline adapters implemented; runtimes unqualified

The application invokes ffprobe only through a fixed argument array. It never uses a shell, accepts
an executable path from the browser, or inspects a remote URL. The adapter requires an absolute
operator-configured executable, its lowercase SHA-256, and the exact first line produced by
`ffprobe -version`. A mismatch fails closed.

Inspection uses `-v error -protocol_whitelist file -show_format -show_streams -of json` against an
application-resolved local asset path. Process time and stdout/stderr are bounded. Only the first
audio and video streams are recorded in v1; no stream is selected automatically for rendering.

Measured duration is stored in integer milliseconds, frame rate as an exact rational pair, and
audio duration as sample rate plus integer sample count. Upload magic-byte checks are not a
substitute for ffprobe inspection.

## Operator qualification

Review the chosen distribution, configure flags, linked codecs, licence obligations, provenance,
and signature/hash evidence before enabling it. On PowerShell, record evidence without copying the
binary into this repository:

```powershell
& 'C:\approved-tools\ffprobe.exe' -version
(Get-FileHash -Algorithm SHA256 'C:\approved-tools\ffprobe.exe').Hash.ToLowerInvariant()
```

Put the exact values in the external `.env` using the `VIDEO_APP_FFPROBE_*` settings documented in
`.env.example`. Do not infer a pin from a package name or moving download URL.

## Rough-cut rendering

The optional `ffmpeg-rough-cut-v1` worker consumes only an immutable, approved manifest created by
the application. Each item pins one current shot revision, an approved storyboard image version and
checksum, and an approved recorded-dialogue asset version and checksum. TTS text, browser paths,
remote URLs, and unapproved media are not renderer inputs.

The Phase 7A Telugu-film profile is locked to 1280x720 at 24/1 fps. The project creation UI uses
that profile for `telugu_short_film_900`; standard projects retain their existing 30/1 fps default.
Submission rejects a project whose saved export settings do not exactly match the qualified worker.

The worker requires separately configured absolute FFmpeg and ffprobe executable paths, lowercase
SHA-256 values, and exact first version lines. Both executables are verified at startup. Commands use
fixed argument arrays with `-nostdin`; no shell is used. Images are scaled with aspect-ratio
preservation and letterboxed to the project export resolution. Dialogue is trimmed or padded to the
shot duration. Each shot is encoded as fixed H.264 video plus 48 kHz PCM audio in a Matroska
intermediate with an application-controlled name. The homogeneous intermediates are concatenated;
video is stream-copied and audio is AAC-encoded once for the final MP4. This avoids accumulating
per-shot AAC frame padding across a long film. The complete film is never decoded into Python
memory.

The adapter bounds item count, duration, process deadlines, log output, and resolved input files. It
re-hashes every input before use, verifies the final dimensions, frame count, and duration with the
pinned ffprobe, and returns only one temporary MP4 to the existing atomic artifact store. Per-run
intermediates are removed on success, cancellation, or failure.

Runtime enablement is fail-closed and requires an operator-reviewed qualification report matching
both executable pins. The report must demonstrate a real image-plus-audio export, measured output,
cancellation cleanup, and exact input-hash enforcement. This phase does not implement TTS, lip-sync,
final sound mixing, or claim that a rough cut passes the 90/180/900-second real-media gates.

## Final timeline rendering

The optional `ffmpeg-timeline-render-v1` worker consumes only the project's current approved
timeline through the canonical leased generation queue. Its immutable manifest freezes the
timeline revision/fingerprint, exact project profile, asset versions/checksums/storage keys,
application-authored titles, and captions. V1 accepts one contiguous layer-zero visual track and
at most 32 explicit audio items. Video audio is always ignored.

Each image, video, or title segment is normalized independently to a homogeneous H.264 Matroska
intermediate. The worker concatenates those visuals, mixes only declared audio into stereo 48 kHz
AAC, and burns an application-authored ASS file using an exact hashed Telugu-capable font. Text is
escaped into the ASS file and never becomes an executable, path, remote URL, or shell argument.
Pinned ffprobe must confirm video and audio streams, dimensions, frame count, sample rate, channels,
and duration before the existing artifact store publishes the MP4.

Enablement requires an operator-reviewed report matching the exact FFmpeg, ffprobe, font, and
fixed-duration profile. The opt-in harness retains a review MP4 and deliberately writes
`pending_operator_review`; an operator must inspect Telugu glyphs, title/caption presentation, and
the audio mix before changing the status and review fields. A 900-second duration does not prove
film quality or satisfy the separate 90/180/900-second acceptance sequence.
