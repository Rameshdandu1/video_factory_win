# Generation Contract v1

Status: Draft; field names and semantics become stable when first implemented.

## Generation request

Required concepts:

- `prompt`: non-empty user text after boundary validation.
- `mode`: initially `text_to_video` only.
- `model`: application model identifier, never an unchecked local path.
- `width` and `height`: supported positive dimensions.
- `frame_count`: supported positive frame count.
- `seed`: explicit integer; generate and persist one when omitted by the caller.
- `parameters`: typed, versioned backend-neutral settings.

Backend-only flags must not be added to the public request. Represent portable capabilities in the domain and keep Wan2.1 tuning inside its adapter configuration.

## Job states

```text
queued -> running -> succeeded
   |         |          
   +-------> cancelled
   |         |
   +--------> failed
```

Terminal states are `succeeded`, `failed`, and `cancelled`. A terminal job never returns to a non-terminal state. Cancellation is requested idempotently; workers must not publish success after cancellation has won the state transition.

## Result

A successful result records job ID, model and upstream revision, normalized request, seed, output media type, dimensions, frame count/duration when known, checksum, storage reference, creation time, and non-secret provenance.

## Failure

Failures expose a stable error code, safe message, retryability, and correlation/job ID. Raw exceptions, credentials, prompts, local paths, and stack traces are not public contract fields.

