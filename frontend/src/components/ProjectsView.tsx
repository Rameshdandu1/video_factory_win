import { type SyntheticEvent, useEffect, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type {
  AspectRatio,
  AssetKind,
  FilmApprovalRequest,
  FilmSceneSave,
  FilmShotSave,
  FilmWorkspace,
  MediaAsset,
  Project,
  ProjectDraft,
  ProjectMode,
  ProjectPreset,
  RightsDeclaration,
  TimelineDraft,
  TimelineRevision,
} from '../api/contracts'
import { ProjectFilmBible } from './ProjectFilmBible'
import { FilmReadinessPanel } from './FilmReadinessPanel'
import { StartingFrameComposer } from './StartingFrameComposer'
import { ReferenceVideoGuidance } from './ReferenceVideoGuidance'
import { RoughCutPanel } from './RoughCutPanel'
import { TimelineRenderPanel } from './TimelineRenderPanel'

function exportFor(aspectRatio: AspectRatio) {
  if (aspectRatio === '9:16') return { width: 720, height: 1280 }
  if (aspectRatio === '1:1') return { width: 1080, height: 1080 }
  return { width: 1280, height: 720 }
}

export function ProjectsView() {
  const [projects, setProjects] = useState<Project[]>([])
  const [title, setTitle] = useState('')
  const [language, setLanguage] = useState('en')
  const [mode, setMode] = useState<ProjectMode>('short')
  const [durationSeconds, setDurationSeconds] = useState(30)
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('16:9')
  const [preset, setPreset] = useState<ProjectPreset>('standard')
  const [titlesWithinTarget, setTitlesWithinTarget] = useState(true)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [assets, setAssets] = useState<MediaAsset[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [assetKind, setAssetKind] = useState<AssetKind>('audio')
  const [rights, setRights] = useState<RightsDeclaration>('permissioned')
  const [uploading, setUploading] = useState(false)
  const [inspectingAssetId, setInspectingAssetId] = useState<string | null>(null)
  const [timelines, setTimelines] = useState<TimelineRevision[]>([])
  const [timelineJson, setTimelineJson] = useState('')
  const [savingTimeline, setSavingTimeline] = useState(false)
  const [filmWorkspace, setFilmWorkspace] = useState<FilmWorkspace | null>(null)
  const [sceneJson, setSceneJson] = useState(
    JSON.stringify(
      {
        position: 0,
        title: 'Scene 1',
        target_duration_ms: 90_000,
        telugu_script: 'తెలుగు సంభాషణ',
        pronunciation_notes: 'Review every name and dialogue line with a Telugu speaker.',
        continuity: {
          location: 'Describe the location',
          lighting: 'Describe the lighting',
          wardrobe: 'Describe every character wardrobe',
          props: 'List continuity props',
          physical_state: 'Describe visible physical state',
          character_positions: 'Describe screen positions and eyelines',
        },
      },
      null,
      2,
    ),
  )
  const [shotJson, setShotJson] = useState('')
  const [approvalJson, setApprovalJson] = useState(
    JSON.stringify(
      { stage: 'telugu_script', scene_id: null, shot_id: null, evidence_asset_id: null },
      null,
      2,
    ),
  )
  const [savingFilm, setSavingFilm] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void videoApi
      .listProjects(50, controller.signal)
      .then((page) => setProjects(page.items))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load projects.')
        }
      })
    return () => controller.abort()
  }, [])

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    const dimensions = exportFor(aspectRatio)
    const draft: ProjectDraft = {
      title: title.trim(),
      language,
      mode,
      target_duration_ms: durationSeconds * 1000,
      aspect_ratio: aspectRatio,
      export_settings: {
        ...dimensions,
        fps_numerator: preset === 'telugu_short_film_900' ? 24 : 30,
        fps_denominator: 1,
      },
      providers: {
        video: 'wan21',
        speech: 'uploaded',
        lip_sync: null,
        caption_alignment: null,
      },
      budget_policy: {
        max_compute_seconds: null,
        max_cost_micros: null,
        automatic_expensive_retries: 0,
      },
      preset,
      titles_and_credits_within_target: titlesWithinTarget,
    }
    setPending(true)
    setMessage(null)
    try {
      const project = await videoApi.createProject(draft)
      setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)])
      setTitle('')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to create the project.')
    } finally {
      setPending(false)
    }
  }

  async function selectProject(projectId: string) {
    setSelectedProjectId(projectId)
    setMessage(null)
    try {
      const project = projects.find((item) => item.id === projectId)
      const filmRequest =
        project?.preset === 'telugu_short_film_900'
          ? videoApi.getFilmWorkspace(projectId)
          : Promise.resolve(null)
      const [assetPage, timelinePage, film] = await Promise.all([
        videoApi.listProjectAssets(projectId),
        videoApi.listTimelineRevisions(projectId),
        filmRequest,
      ])
      setAssets(assetPage.items)
      setTimelines(timelinePage.items)
      setFilmWorkspace(film)
      if (project !== undefined) {
        setTimelineJson(
          JSON.stringify(
            {
              duration_ms: project.target_duration_ms,
              items: [
                {
                  kind: 'title_card',
                  start_ms: 0,
                  duration_ms: project.target_duration_ms,
                  layer: 0,
                  asset_id: null,
                  text: project.title,
                },
              ],
              captions: [],
            },
            null,
            2,
          ),
        )
      }
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to load project assets.')
    }
  }

  async function createTimeline() {
    if (selectedProjectId === null) return
    setSavingTimeline(true)
    setMessage(null)
    try {
      const parsed: unknown = JSON.parse(timelineJson)
      if (typeof parsed !== 'object' || parsed === null) throw new Error('invalid JSON')
      const timeline = await videoApi.createTimelineRevision(
        selectedProjectId,
        parsed as TimelineDraft,
      )
      setTimelines((current) => [timeline, ...current])
    } catch (error: unknown) {
      setMessage(
        isApiClientError(error)
          ? error.message
          : 'Timeline JSON is invalid or does not match the project.',
      )
    } finally {
      setSavingTimeline(false)
    }
  }

  async function approveTimeline(timelineId: string) {
    if (selectedProjectId === null) return
    const project = projects.find((item) => item.id === selectedProjectId)
    if (project === undefined) return
    setMessage(null)
    try {
      const approved = await videoApi.approveTimelineRevision(
        project.id,
        timelineId,
        project.version,
      )
      setTimelines((current) => current.map((item) => (item.id === approved.id ? approved : item)))
      setProjects((current) =>
        current.map((item) =>
          item.id === project.id
            ? { ...item, version: item.version + 1, approved_timeline_revision_id: approved.id }
            : item,
        ),
      )
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to approve the timeline.')
    }
  }

  async function upload(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    if (selectedProjectId === null || file === null) return
    const form = event.currentTarget
    setUploading(true)
    setMessage(null)
    try {
      const asset = await videoApi.uploadProjectAsset(selectedProjectId, file, assetKind, rights)
      setAssets((current) => [asset, ...current])
      setFile(null)
      form.reset()
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to upload the asset.')
    } finally {
      setUploading(false)
    }
  }

  async function inspect(assetId: string) {
    if (selectedProjectId === null) return
    setInspectingAssetId(assetId)
    setMessage(null)
    try {
      const inspected = await videoApi.inspectProjectAsset(selectedProjectId, assetId)
      setAssets((current) => current.map((item) => (item.id === inspected.id ? inspected : item)))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to inspect the asset.')
    } finally {
      setInspectingAssetId(null)
    }
  }

  async function saveScene() {
    if (selectedProjectId === null) return
    setSavingFilm(true)
    setMessage(null)
    try {
      const scene = await videoApi.saveFilmScene(
        selectedProjectId,
        JSON.parse(sceneJson) as FilmSceneSave,
      )
      setFilmWorkspace((current) => ({
        scenes: [scene, ...(current?.scenes.filter((item) => item.id !== scene.id) ?? [])],
        shots: current?.shots ?? [],
        approvals: current?.approvals ?? [],
      }))
      if (shotJson.trim() === '') {
        setShotJson(
          JSON.stringify(
            {
              scene_id: scene.id,
              position: 0,
              target_duration_ms: 8_000,
              description: 'Describe one independently generated shot',
              reference_workflow: 'reference_generation',
              character_reference_asset_ids: ['replace-with-image-asset-id'],
              dialogue_workflow: 'recorded',
              storyboard_asset_id: 'replace-with-storyboard-image-asset-id',
              source_footage_asset_id: null,
              recorded_dialogue_asset_id: 'replace-with-audio-asset-id',
            },
            null,
            2,
          ),
        )
      }
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Scene JSON is invalid.')
    } finally {
      setSavingFilm(false)
    }
  }

  async function saveShot() {
    if (selectedProjectId === null) return
    setSavingFilm(true)
    setMessage(null)
    try {
      const shot = await videoApi.saveFilmShot(
        selectedProjectId,
        JSON.parse(shotJson) as FilmShotSave,
      )
      setFilmWorkspace((current) => ({
        scenes: current?.scenes ?? [],
        shots: [shot, ...(current?.shots.filter((item) => item.id !== shot.id) ?? [])],
        approvals: current?.approvals ?? [],
      }))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Shot JSON is invalid.')
    } finally {
      setSavingFilm(false)
    }
  }

  async function approveFilm() {
    if (selectedProjectId === null) return
    setSavingFilm(true)
    setMessage(null)
    try {
      const approval = await videoApi.approveFilmSubject(
        selectedProjectId,
        JSON.parse(approvalJson) as FilmApprovalRequest,
      )
      setFilmWorkspace((current) => ({
        scenes: current?.scenes ?? [],
        shots: current?.shots ?? [],
        approvals: [approval, ...(current?.approvals ?? [])],
      }))
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Approval JSON is invalid.')
    } finally {
      setSavingFilm(false)
    }
  }

  const selectedProject = projects.find((item) => item.id === selectedProjectId)
  const approvedTimelineId = selectedProject?.approved_timeline_revision_id ?? null

  return (
    <main id="workspace" className="projects-workspace">
      <section className="project-create" aria-labelledby="project-create-title">
        <p className="eyebrow">Project workflow v2</p>
        <h1 id="project-create-title">Create a video project</h1>
        <p className="project-cost-label">Self-hosted; infrastructure costs apply.</p>
        <form onSubmit={(event) => void submit(event)}>
          <label className="field">
            <span>Project title</span>
            <input
              required
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <div className="form-grid">
            <label className="field">
              <span>Preset</span>
              <select
                value={preset}
                onChange={(event) => {
                  const nextPreset = event.target.value as ProjectPreset
                  setPreset(nextPreset)
                  if (nextPreset === 'telugu_short_film_900') {
                    setLanguage('te')
                    setMode('long')
                    setDurationSeconds(900)
                    setAspectRatio('16:9')
                  }
                }}
              >
                <option value="standard">Standard project</option>
                <option value="telugu_short_film_900">15-minute Telugu short film</option>
              </select>
            </label>
            <label className="field">
              <span>Language</span>
              <select
                value={language}
                disabled={preset === 'telugu_short_film_900'}
                onChange={(event) => setLanguage(event.target.value)}
              >
                <option value="en">English</option>
                <option value="te">Telugu</option>
                <option value="hi">Hindi</option>
              </select>
            </label>
            <label className="field">
              <span>Workflow</span>
              <select
                value={mode}
                disabled={preset === 'telugu_short_film_900'}
                onChange={(event) => {
                  const nextMode = event.target.value as ProjectMode
                  setMode(nextMode)
                  setDurationSeconds(nextMode === 'short' ? 30 : 300)
                }}
              >
                <option value="short">Short video</option>
                <option value="long">Chapter-based long video</option>
              </select>
            </label>
            <label className="field">
              <span>Finished duration</span>
              <select
                value={durationSeconds}
                disabled={preset === 'telugu_short_film_900'}
                onChange={(event) => setDurationSeconds(Number(event.target.value))}
              >
                {(preset === 'telugu_short_film_900'
                  ? [900]
                  : mode === 'short'
                    ? [15, 30, 60]
                    : [300, 600, 1800, 3600]
                ).map((seconds) => (
                  <option key={seconds} value={seconds}>
                    {seconds < 60
                      ? `${String(seconds)} seconds`
                      : `${String(seconds / 60)} minutes`}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Aspect ratio</span>
              <select
                value={aspectRatio}
                onChange={(event) => setAspectRatio(event.target.value as AspectRatio)}
              >
                <option value="16:9">Landscape 16:9</option>
                <option value="9:16">Vertical 9:16</option>
                <option value="1:1">Square 1:1</option>
              </select>
            </label>
          </div>
          {preset === 'telugu_short_film_900' ? (
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={titlesWithinTarget}
                onChange={(event) => setTitlesWithinTarget(event.target.checked)}
              />
              <span>Count titles and credits within the 900-second target</span>
            </label>
          ) : null}
          <button className="button button--primary" disabled={pending || title.trim() === ''}>
            {pending ? 'Creating project…' : 'Create project'}
          </button>
        </form>
        {message === null ? null : (
          <p className="project-message" role="alert">
            {message}
          </p>
        )}
      </section>

      <section className="project-list" aria-labelledby="projects-title">
        <p className="eyebrow">Server-authoritative drafts</p>
        <h2 id="projects-title">Projects</h2>
        {projects.length === 0 ? (
          <p>No projects yet. Create the first approved workflow draft.</p>
        ) : (
          <ul>
            {projects.map((project) => (
              <li key={project.id}>
                <button type="button" onClick={() => void selectProject(project.id)}>
                  <strong>{project.title}</strong>
                  <span>{selectedProjectId === project.id ? 'Selected' : 'Manage assets'}</span>
                </button>
                <span>{project.mode === 'short' ? 'Short video' : 'Long video'}</span>
                <span>
                  {project.preset === 'telugu_short_film_900'
                    ? 'Telugu film · 900 seconds'
                    : 'Standard preset'}
                </span>
                <span>
                  {project.language.toUpperCase()} · {project.aspect_ratio}
                </span>
                <span>
                  Revision {project.version} · {project.state}
                </span>
              </li>
            ))}
          </ul>
        )}
        {selectedProjectId === null ? null : (
          <div className="asset-manager">
            <h3>Permissioned media assets</h3>
            <p>PNG, JPEG, WAV, or MP4. Maximum size is configured by the server.</p>
            <form onSubmit={(event) => void upload(event)}>
              <label className="field">
                <span>Media file</span>
                <input
                  required
                  type="file"
                  accept="image/png,image/jpeg,audio/wav,video/mp4"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <div className="form-grid">
                <label className="field">
                  <span>Asset kind</span>
                  <select
                    value={assetKind}
                    onChange={(event) => setAssetKind(event.target.value as AssetKind)}
                  >
                    <option value="image">Image</option>
                    <option value="audio">Audio</option>
                    <option value="video">Video</option>
                  </select>
                </label>
                <label className="field">
                  <span>Rights declaration</span>
                  <select
                    value={rights}
                    onChange={(event) => setRights(event.target.value as RightsDeclaration)}
                  >
                    <option value="owned">I own this media</option>
                    <option value="licensed">Licensed for this use</option>
                    <option value="permissioned">Permission granted</option>
                    <option value="public_domain">Public domain</option>
                  </select>
                </label>
              </div>
              <button className="button button--primary" disabled={uploading || file === null}>
                {uploading ? 'Uploading asset…' : 'Upload asset'}
              </button>
            </form>
            {assets.length === 0 ? (
              <p>No assets uploaded.</p>
            ) : (
              <ul className="asset-list">
                {assets.map((asset) => (
                  <li key={asset.id}>
                    <strong>{asset.original_filename}</strong>
                    <span>
                      {asset.kind} · {asset.rights} · {String(asset.size_bytes)} bytes
                    </span>
                    <code>{asset.id}</code>
                    {asset.metadata === null ? (
                      <button
                        type="button"
                        className="button button--secondary"
                        disabled={inspectingAssetId !== null}
                        onClick={() => void inspect(asset.id)}
                      >
                        {inspectingAssetId === asset.id ? 'Inspecting…' : 'Inspect media'}
                      </button>
                    ) : (
                      <span>
                        {String(asset.metadata.duration_ms)} ms
                        {asset.metadata.width === null
                          ? ''
                          : ` · ${String(asset.metadata.width)}×${String(asset.metadata.height)}`}
                        {asset.metadata.sample_rate === null
                          ? ''
                          : ` · ${String(asset.metadata.sample_rate)} Hz`}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <div className="timeline-editor">
              <h3>Timeline and captions</h3>
              <p>Integer milliseconds only. Saving creates an immutable revision.</p>
              <label className="field">
                <span>Timeline JSON</span>
                <textarea
                  rows={14}
                  value={timelineJson}
                  onChange={(event) => setTimelineJson(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="button button--primary"
                disabled={savingTimeline || timelineJson.trim() === ''}
                onClick={() => void createTimeline()}
              >
                {savingTimeline ? 'Saving revision…' : 'Save timeline revision'}
              </button>
              {timelines.length === 0 ? (
                <p>No timeline revisions.</p>
              ) : (
                <ul className="asset-list">
                  {timelines.map((timeline) => (
                    <li key={timeline.id}>
                      <strong>Revision {timeline.revision}</strong>
                      <span>
                        {String(timeline.duration_ms)} ms · {timeline.fingerprint.slice(0, 12)}
                      </span>
                      {timeline.approved_at === null ? (
                        <button
                          type="button"
                          className="button button--secondary"
                          onClick={() => void approveTimeline(timeline.id)}
                        >
                          Approve revision
                        </button>
                      ) : (
                        <span>Approved</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {approvedTimelineId === null ? null : (
                <TimelineRenderPanel
                  key={`${selectedProjectId}:${approvedTimelineId}`}
                  projectId={selectedProjectId}
                  timelineId={approvedTimelineId}
                />
              )}
            </div>
            {selectedProject?.preset === 'telugu_short_film_900' && filmWorkspace !== null ? (
              <div className="film-editor">
                <h3>Telugu short-film workflow</h3>
                <p>
                  Scenes own script and continuity. Shots are approved independently; seed reuse is
                  not accepted as identity preservation.
                </p>
                <div className="film-gate-summary">
                  <span>{filmWorkspace.scenes.length} scenes</span>
                  <span>{filmWorkspace.shots.length} shots</span>
                  <span>{filmWorkspace.approvals.length} approvals</span>
                </div>
                <FilmReadinessPanel
                  projectId={selectedProject.id}
                  refreshToken={[
                    ...filmWorkspace.scenes.map((item) => `${item.id}:${item.content_fingerprint}`),
                    ...filmWorkspace.shots.map((item) => `${item.id}:${item.content_fingerprint}`),
                    ...filmWorkspace.approvals.map((item) => item.id),
                  ].join('|')}
                />
                <ProjectFilmBible projectId={selectedProject.id} shots={filmWorkspace.shots} />
                <StartingFrameComposer projectId={selectedProject.id} shots={filmWorkspace.shots} />
                <ReferenceVideoGuidance
                  projectId={selectedProject.id}
                  shots={filmWorkspace.shots}
                />
                <RoughCutPanel key={selectedProject.id} projectId={selectedProject.id} />
                <label className="field">
                  <span>Scene JSON</span>
                  <textarea
                    rows={16}
                    value={sceneJson}
                    onChange={(event) => setSceneJson(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={savingFilm}
                  onClick={() => void saveScene()}
                >
                  Save scene revision
                </button>
                <label className="field">
                  <span>Independent shot JSON</span>
                  <textarea
                    rows={16}
                    value={shotJson}
                    placeholder="Save a scene first, then replace asset IDs."
                    onChange={(event) => setShotJson(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={savingFilm || shotJson.trim() === ''}
                  onClick={() => void saveShot()}
                >
                  Save shot revision
                </button>
                <label className="field">
                  <span>Approval JSON</span>
                  <textarea
                    rows={7}
                    value={approvalJson}
                    onChange={(event) => setApprovalJson(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={savingFilm}
                  onClick={() => void approveFilm()}
                >
                  Record approval
                </button>
                <p className="film-warning">
                  Required real-media sequence: approved 90-second dialogue scene, then 3-minute
                  sequence, then the 15-minute film. Duration alone never passes acceptance.
                </p>
                <ul className="asset-list">
                  {filmWorkspace.scenes.map((scene) => (
                    <li key={scene.id}>
                      <strong>{scene.draft.title}</strong>
                      <code>{scene.id}</code>
                      <span>Scene revision {scene.version}</span>
                    </li>
                  ))}
                  {filmWorkspace.shots.map((shot) => (
                    <li key={shot.id}>
                      <strong>{shot.draft.description}</strong>
                      <code>{shot.id}</code>
                      <span>Shot revision {shot.version}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </section>
    </main>
  )
}
