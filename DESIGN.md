# Design System: Video Factory

Status: Accepted for Frontend UI v1 on 2026-08-21

This file is the visual and interaction source of truth for the browser client. Read it with [Frontend UI Specification v1](docs/specifications/frontend-ui-v1.md) before making UI decisions. Deviations require explicit approval and a recorded rationale.

## Product context

- **What this is:** A local video-generation workspace that turns one text prompt into a durable, inspectable generation job and MP4.
- **Who it serves:** A creator or operator running the application on their own workstation.
- **Project type:** A focused creative tool with operational job-state visibility, not a marketing site or general administration dashboard.
- **Memorable quality:** The current state of expensive work is unmistakable. The user should always know what was requested, whether the system is waiting or working, and what action is safe next.

## Design principles

### The video is the visual center

Interface decoration stays quiet so prompts, status, and generated media carry the page. Successful output receives the largest uninterrupted surface.

### State is more important than spectacle

Every contract state maps to one stable visible label: `queued` is **Queued**, `running` is **Running**, `succeeded` is **Ready**, `failed` is **Failed**, and `cancelled` is **Cancelled**. Stable color and placement reinforce the text. An indeterminate running state never becomes a fictional percentage or ETA.

### Expensive actions feel deliberate

Generate and cancel controls have clear labels, visible pending states, and enough separation to prevent accidental activation. The design does not use ambiguous icon-only primary actions.

### Dense, not cramped

The application should feel like a capable desktop tool. Metadata can be compact, but form controls, media, errors, and touch targets retain comfortable spacing.

## Aesthetic direction

- **Direction:** Cinematic utility.
- **Decoration:** Minimal and intentional.
- **Mood:** Dark, precise, calm, and slightly warm. Near-black surfaces frame media; amber marks the creative action; cool blue marks activity.
- **Avoid:** purple gradients, glassmorphism, soft bubble cards, decorative hero art, uniform pills, oversized marketing copy, and animation without state meaning.
- **Surface model:** Dark mode only for v1. A theme switch is not part of the MVP.

## Typography

The application uses named operating-system fonts so local development and the offline application do not depend on a font CDN.

| Role              | Font stack                                                         | Use                                                                    |
| ----------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Headings          | `Bahnschrift`, `Segoe UI Variable Display`, `Segoe UI`, sans-serif | `h1` and `h2` section headings                                         |
| Body and controls | `Segoe UI Variable Text`, `Segoe UI`, `system-ui`, sans-serif      | Product name, prompts, labels, controls, messages, and supporting copy |
| Data              | `Cascadia Mono`, `Consolas`, monospace                             | Seeds, job IDs, checksums, dimensions, frame counts, and timestamps    |

Use tabular numerals for changing progress and metadata. Do not uppercase paragraphs or button labels.

### Type scale

| Role       | Implemented size / line height              | Use                                        |
| ---------- | ------------------------------------------- | ------------------------------------------ |
| `h1`       | `clamp(1.8rem, 2.4vw, 2.5rem) / 1.05`       | Generation composer heading                |
| `h2`       | `clamp(1.35rem, 1.7vw, 1.8rem) / 1.05`      | Selected-job and recent-job headings       |
| Body       | `1rem / normal`                             | Browser base and controls                  |
| Supporting | `0.66rem` through `0.97rem`, role-dependent | Labels, metadata, status, and compact copy |

Hierarchy comes from size, spacing, and weight rather than many font styles. Controls and labels use the Segoe body stack; only the `h1` and `h2` selectors use Bahnschrift.

## Color

Use color through CSS custom properties. Never place a raw hex value inside a component rule when a semantic token exists.

### Warm-neutral surfaces and text

| CSS variable              | Value     | Purpose                                      |
| ------------------------- | --------- | -------------------------------------------- |
| `--canvas`                | `#0e0d0c` | Browser canvas and form-control background   |
| `--surface`               | `#141311` | Composer, detail, and queue panels           |
| `--surface-raised`        | `#1a1815` | Raised and loading surfaces                  |
| `--surface-hover`         | `#211e1a` | Hovered and selected job-row surface         |
| `--surface-attention`     | `#211b13` | Cancellation-requested notice                |
| `--surface-danger`        | `#231613` | Page-level error notice                      |
| `--surface-danger-subtle` | `#201411` | Inline failure and unavailable-output region |
| `--surface-success`       | `#111916` | Successful output summary                    |
| `--surface-preview`       | `#090908` | Video surround                               |
| `--line`                  | `#34302a` | Default separators and control borders       |
| `--line-soft`             | `#25221e` | Subtle separators                            |
| `--line-hover`            | `#5b5349` | Hover border                                 |
| `--line-preview`          | `#3b3732` | Empty-preview framing                        |
| `--text`                  | `#f2ece3` | Primary warm-white text                      |
| `--text-muted`            | `#aaa299` | Secondary copy and metadata                  |
| `--text-dim`              | `#8d857c` | Tertiary technical text                      |
| `--text-placeholder`      | `#857e76` | Input placeholder text                       |

### Actions and semantics

| CSS variable      | Value     | Purpose                                         |
| ----------------- | --------- | ----------------------------------------------- |
| `--accent`        | `#eca451` | Generate action and selected-job edge           |
| `--accent-strong` | `#ffc171` | Primary-action hover                            |
| `--accent-ink`    | `#1d1307` | Text on the accent                              |
| `--focus`         | `#78b7ff` | Keyboard focus ring                             |
| `--success`       | `#78bea0` | Connected and succeeded state                   |
| `--danger`        | `#e77a68` | Failed state, errors, and cancellation action   |
| `--queued`        | `#c8a977` | Queued state                                    |
| `--running`       | `#78b7ff` | Running state; intentionally matches focus blue |
| `--cancelled`     | `#958e86` | Cancelled state                                 |

Status color always appears with the exact status word. Error and success regions use a subtle tinted border or background, not large saturated fills. Amber is reserved for primary creation and queued attention; it does not decorate unrelated content.

## Spacing

- **Base unit:** 4 CSS pixels.
- **Density:** Comfortable controls with compact metadata.
- **Control height:** Buttons are at least 44 pixels; composer text inputs and selects are 46 pixels; the compact queue filter select is 42 pixels.
- **Panel padding:** Composer and detail padding scale up to `--space-10`; below 768 pixels they use `--space-6` vertically and `--space-4` horizontally.
- **Text measure:** Prompt help and errors stay below 70 characters per line where practical.

| CSS variable | Value     |
| ------------ | --------- |
| `--space-1`  | `0.25rem` |
| `--space-2`  | `0.5rem`  |
| `--space-3`  | `0.75rem` |
| `--space-4`  | `1rem`    |
| `--space-5`  | `1.25rem` |
| `--space-6`  | `1.5rem`  |
| `--space-8`  | `2rem`    |
| `--space-10` | `2.5rem`  |
| `--space-12` | `3rem`    |

Do not solve hierarchy by wrapping every group in another card. Prefer a heading, spacing, and one separator.

## Layout

### App shell

- The page fills at least the viewport height on `--canvas`.
- A compact sticky header holds the product name at left and API health plus the labeled **Refresh jobs** action at right.
- Main content is centered, spans the available width, and stops growing at 1600 pixels.
- The wide desktop workspace has three panels in source order: composer, selected-job detail, and recent-job queue. The composer is 320 to 390 pixels, the queue is 300 to 370 pixels, and detail receives the flexible center column.
- Generated media uses its natural aspect ratio within a stable dark preview frame and never stretches.

### Responsive breakpoints

- **Wide, above 1180 pixels:** Three columns show composer, selected detail, and recent jobs together. At 1440 pixels, the outer columns widen within their fixed bounds.
- **Medium, 769 through 1180 pixels:** Composer and selected detail form two columns. Recent jobs span the next row, with three job columns above 1024 pixels and two at 1024 pixels or below.
- **Narrow, below 768 pixels:** One reading column in this order: header, composer, selected job, recent jobs. Panel padding drops to 16 pixels.
- **Compact, below 480 pixels:** Header actions wrap into a labeled second row; forms, metadata, and output actions use one column.

The page must not require horizontal scrolling at 320 CSS pixels. Long job IDs and checksums wrap or truncate visually with an accessible full value.

### Radius and depth

| CSS variable  | Value | Use                                               |
| ------------- | ----- | ------------------------------------------------- |
| `--radius-sm` | `4px` | Inputs, buttons, notices, and compact elements    |
| `--radius-md` | `8px` | Reserved for a larger bounded surface when needed |

The implemented layout uses one-pixel borders rather than card shadows. Job rows have square edges, and circular geometry is limited to status dots and the preview aperture.

## Core patterns

### Header

Keep the product name left aligned. A right-side action group contains API state, shown as a small dot plus **API connected**, **Connecting to API**, or **API unavailable**, followed by the labeled **Refresh jobs** secondary button. While the list refresh is in flight, the button is disabled and reads **Refreshing…**. On compact screens, the action group wraps below the brand without losing either label.

### Generation composer

- Prompt is the largest control and starts at seven visible lines.
- Prompt character count and seed guidance share the label row above their controls; below 375 pixels, each label row stacks.
- Model occupies a full-width row. Resolution and frame count share a two-column grid that becomes one column below 480 pixels.
- **Generate video** uses the amber primary style and occupies a stable location.
- Submission pending changes the label to **Sending to queue…** and preserves layout width.

### Job rows

- Status and created time share the first line.
- Prompt text is clamped to two lines. Model, resolution, frame count, seed, created-or-completed time, and a compact job ID remain secondary.
- Hover and selection share `--surface-hover`, but the selected row also has a two-pixel `--accent` left edge and `aria-current`.
- Rows are real buttons with a visible focus ring and an **Open generation {job ID}** accessible name.

### Selected job

- State and safe next action appear before technical metadata.
- Queued and running jobs use an indeterminate activity treatment only. If reliable progress exists, use a native or correctly labelled progress bar.
- A cancellation request keeps the running label until the API reports `cancelled` and adds the text **Cancellation requested**.
- Failure shows safe message, code, retryability, and correlation ID in a bordered error region.
- Success gives the preview priority, followed by **MP4 ready**, **Download video**, and a compact size, duration, and checksum definition list.
- A media-load error keeps the job and result metadata visible and adds: **This video output is currently unavailable. Refresh the job before trying again.**
- A seed outside JavaScript's safe-integer range is labelled **Stored by server**. Never print the rounded browser number as if it were exact.

### Buttons

- **Primary:** amber fill, dark ink, used once per working region.
- **Secondary:** transparent surface, light text, visible border, and `--surface-hover` on hover.
- **Danger:** transparent or dark red-tinted surface with danger border; use only for cancellation.
- **Disabled:** remains legible, removes hover, and never uses opacity below 58 percent.
- Every pending action uses explicit text such as **Sending to queue…**, **Requesting cancellation…**, or **Refreshing…**.

### Forms and errors

Labels sit above controls. Help text precedes validation text. Invalid controls use danger border plus a concise message linked with `aria-describedby`. Connection-level errors remain banners or panel messages and do not mark unrelated fields invalid.

### Empty states

Empty job history uses the heading **No generations yet** and supporting line **Your next job will appear here.** A filtered empty list retains the same heading and changes only the supporting line to **No jobs match this status.** Do not add an illustration merely to occupy space. A missing selection says **Select a generation to inspect its settings, state, and output.** without hiding the composer.

## Motion

- **Approach:** Minimal and functional.
- **Control transitions:** 140 milliseconds for background, border, and color feedback.
- **Connection pulse:** 1.4 seconds with `ease-in-out` while connecting.
- **Indeterminate progress:** 1.6 seconds with `ease-in-out` and a textual queued or running label. Never animate a percentage.
- **Loading skeleton:** 1.5 seconds linear.

Under `prefers-reduced-motion: reduce`, remove looping decorative motion and make transitions immediate or nearly immediate. Polling must never cause the whole list to flash or shift.

## Accessibility

- Target WCAG 2.2 AA contrast and interaction behavior.
- Use semantic headings in order and one main landmark.
- Use a visible two-pixel focus ring with a two-pixel offset.
- Pair every icon with text or an accessible name; primary v1 actions remain text-labelled.
- Announce newly submitted jobs, terminal state changes, and new safe errors through restrained live regions.
- Do not announce unchanged data on every 2.5-second poll.
- Preserve native video controls and provide a text download alternative.
- Status, selection, errors, and disabled state must remain understandable without color.

## Content and privacy

- Voice is concise and operational: **Queued**, **Running**, **Cancellation requested**, **MP4 ready**, **Generation stopped**, **Generation cancelled**, and **Output pending**. Failure detail comes from the API's safe message rather than fixed client copy.
- Use **Generate video**, not vague labels such as **Create** or **Go**.
- Avoid claims about quality, speed, ETA, GPU state, or retry success that the API does not prove.
- Show private prompt text only where the local user expects it: the composer, a bounded row excerpt, and selected-job detail.
- Do not put prompt text into the document title, browser storage, console output, analytics, URLs, or download filenames.
- Keep opaque IDs and checksums visually copyable without implying meaning.

## Implementation constraints

- Styles are plain CSS. No utility-CSS framework, component theme, or runtime styling dependency is allowed.
- Components consume the typed native-fetch client; they do not call `fetch` ad hoc throughout the tree.
- `@chenglou/pretext` may assist text layout only and must not define visual tokens or interactive controls.
- Use DESIGN.md tokens and patterns before adding a one-off value.
- A new theme, font asset, component kit, router, remote-data cache, or global store requires explicit approval and an ADR update.

## Decision log

| Date       | Decision                                                  | Rationale                                                                                        |
| ---------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 2026-08-21 | Adopt cinematic utility with dark restrained surfaces     | Generated media stays visually central while job state remains easy to scan                      |
| 2026-08-21 | Use amber for creation and cool semantic colors for state | Creation is distinct from running, success, failure, and cancellation without a gradient palette |
| 2026-08-21 | Use named local Windows font stacks                       | The local application remains usable without a font CDN or another runtime asset dependency      |
| 2026-08-21 | Keep motion minimal and status-driven                     | Long-running work needs calm, truthful updates rather than continuous visual noise               |
