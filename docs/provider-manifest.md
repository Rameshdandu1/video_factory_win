# Provider and Dependency Manifest

Status: Reference-driven Phase 8 review updated 2026-10-13. Entries marked disabled are not
production-ready.

This is an engineering review record, not legal advice. Every provisioned image must retain its own
machine-readable package lock, model manifest, integrity evidence, FFmpeg build configuration, and
required notices. A local hash proves later identity, not initial provenance.

| Provider | Source or model | Reviewed revision | Reported licence | State | Required next evidence |
| --- | --- | --- | --- | --- | --- |
| Existing Wan2.1 T2V | `Wan-Video/Wan2.1` plus the selected T2V checkpoint | Code `9737cba9c1c3c4d04b33fcad41c111989865d315`; model pins in the runtime specification | Upstream model repository reports Apache-2.0 | Implemented; target GPU report absent | Preserve deployed revision; capture Runpod runtime and qualification report |
| FFmpeg / ffprobe | `ffmpeg.org` operator build | Not installed on the inspected Windows host | LGPL-2.1-or-later by default; optional GPL/nonfree components change redistribution obligations | Pinned inspection, rough-cut, and final-timeline adapters implemented; runtimes disabled | Select operator build, record exact version/configuration/hash, verify redistribution obligations, run both qualification harnesses, and review Telugu titles/captions plus the explicit final audio mix |
| Telugu render font | Operator-selected local font file | Exact file unresolved; runtime requires SHA-256 and exact family | Licence depends on selected font and must permit intended rendering/distribution | Required by final-timeline worker; disabled | Select a Telugu-capable font, retain licence/notice, pin file hash/family, and visually review the qualification MP4 before approval |
| Indic Parler-TTS | `ai4bharat/indic-parler-tts` | Candidate model revision `7b527af5ee8ed1f9a28d80b19703ed9bb8ba10ca`; runtime pin unresolved | Model card reports Apache-2.0; training-data annotation licensing has an unresolved upstream question | Disabled | Resolve commercial-use provenance, pin `parler-tts`, voices, dependencies, and qualify Telugu/Hindi/English |
| Kokoro | `hexgrad/Kokoro-82M` and `hexgrad/kokoro` | Candidate model revision `9871713c6a29032f914cee65b617e2b6b3323770`; runtime pin unresolved | Model card reports Apache-2.0 and includes dataset attribution notes | Disabled | Pin runtime/voices and verify English voice identifiers and notices |
| MuseTalk | `TMElyralab/MuseTalk` | Exact code and weight pins unresolved | Repository code license reports MIT and enumerates third-party dependencies; each weight/dependency still requires review | Disabled | Select MuseTalk version, pin source/weights, review face/preprocessing assets, isolate image, qualify real media |
| InfiniteTalk | `MeiGen-AI/InfiniteTalk` | Exact code/weight pins unresolved | Repository reports Apache-2.0 for its models; base Wan I2V and audio encoder require separate review | Disabled, opt-in only | Pin source, multi-person weights, Wan2.1-I2V-14B-480P and audio encoder; qualify speaker mapping and GPU profile |
| WhisperX-compatible alignment | `m-bain/whisperX` | Candidate stable release to be selected; no runtime pin | Code reports BSD-2-Clause; alignment/VAD/diarization models have separate terms and some gated access | Disabled, optional | Select local models per language, record their terms, and qualify segment/word timing honestly |
| Local script assistant | Operator-configured local inference endpoint | No model selected | Unresolved | Disabled, optional | Approve and pin model/server; add schema-constrained, size-bounded adapter |
| Wan2.2 TI2V-5B | `Wan-Video/Wan2.2` and `Wan-AI/Wan2.2-TI2V-5B` | Code `1ea34ff48f87168174e12956e200b1d908b1c5ff`; model `921dbaf3f1674a56f47e83fb80a34bac8a8f203e` | Upstream repository/model report Apache-2.0 | Adapter implemented; disabled until target-GPU report | Produce checkpoint content manifest and approved qualification report with two distinct inputs, output decode, resource threshold, and cancellation evidence |
| VACE performance transfer | `ali-vilab/VACE` and `ali-vilab/VACE-Wan2.1-1.3B-Preview` | Code `48eb44f1c4be87cc65a98bff985a26976841e9f3`; model `c76cda849bfb74d563b95f3db039421e9df2a570` | Repository/model report Apache-2.0 | Adapter implemented; disabled until target-GPU report | Produce checkpoint/FFmpeg manifests and prove approved image + bounded video preprocessing, controls, decode, resources, and cancellation |
| Wan2.2-Animate | `Wan-Video/Wan2.2` and `Wan-AI/Wan2.2-Animate-14B` | Code `29d4a35d32273d5309a3a95250bd4e118d8789b2`; model `cb93a225fbaf1ca100f54e79da8f994995b689b3` | Repository/model report Apache-2.0 | Animation/replacement adapter implemented; disabled until target-GPU report | Produce checkpoint/FFmpeg manifests and separately prove retarget and replacement input roles, controls, decode, resources, and cancellation |

## Reviewed capability facts

- Indic Parler-TTS's model card lists Telugu, Hindi, and English among its supported languages and
  publishes recommended speakers; the application must use only identifiers from the eventual pin.
- Kokoro's reviewed model card is English-tagged. Additional languages are not enabled by this
  manifest.
- MuseTalk accepts source media plus audio through its inference configuration and requires FFmpeg;
  it is the selected first visible single-speaker lip-sync provider once qualified.
- InfiniteTalk documents separate single- and multi-person weights, a Wan2.1 I2V base model, an audio
  encoder, and multi-person JSON input. It must not reuse the existing T2V checkpoint.
- FFmpeg's licence depends on its configure flags and linked codecs. “FFmpeg installed” is therefore
  insufficient provenance.

No model or dependency was downloaded or installed during this review.

The Wan2.2 TI2V, VACE, and Wan Animate pins are enforced by isolated adapters. Each remains disabled
until its matching operator qualification report proves the exact deployed checkpoint/runtime and
input conditioning on authorized GPU. No provider was downloaded or executed during this change.
