import { useEffect, useMemo, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type {
  FilmBibleNameResolution,
  FilmBiblePin,
  FilmBiblePinRole,
  FilmBiblePinSelection,
  FilmBibleSnapshot,
  FilmShot,
  LibraryEntity,
  LibraryVersion,
  LibraryVersionKind,
} from '../api/contracts'

interface ProjectFilmBibleProps {
  projectId: string
  shots: FilmShot[]
}

const roleForVersion: Record<LibraryVersionKind, FilmBiblePinRole> = {
  identity: 'character_identity',
  wardrobe: 'character_wardrobe',
  location_view: 'location_view',
  lighting_variant: 'location_lighting',
  prop_variant: 'prop_variant',
  prop_state: 'prop_state',
  shot_reference: 'shot_reference',
}

function selectionFor(pin: FilmBiblePin): FilmBiblePinSelection {
  return { entity_id: pin.entity_id, version_id: pin.library_version_id, role: pin.role }
}

function pinKey(pin: FilmBiblePin | FilmBiblePinSelection): string {
  const versionId = 'library_version_id' in pin ? pin.library_version_id : pin.version_id
  return `${pin.entity_id}\u0000${pin.role}\u0000${versionId}`
}

export function ProjectFilmBible({ projectId, shots }: ProjectFilmBibleProps) {
  const [entities, setEntities] = useState<LibraryEntity[]>([])
  const [versions, setVersions] = useState<Record<string, LibraryVersion[]>>({})
  const [snapshots, setSnapshots] = useState<FilmBibleSnapshot[]>([])
  const [draftPins, setDraftPins] = useState<FilmBiblePinSelection[]>([])
  const [entityId, setEntityId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [snapshotId, setSnapshotId] = useState('')
  const [mention, setMention] = useState('@')
  const [resolution, setResolution] = useState<FilmBibleNameResolution | null>(null)
  const [shotId, setShotId] = useState('')
  const [bindingKeys, setBindingKeys] = useState<string[]>([])
  const [affected, setAffected] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([
      videoApi.listLibraryEntities(undefined, undefined, controller.signal),
      videoApi.listFilmBibleSnapshots(projectId, controller.signal),
    ])
      .then(async ([entityPage, snapshotPage]) => {
        const versionPages = await Promise.all(
          entityPage.items.map(
            async (entity) =>
              [
                entity.id,
                (await videoApi.listLibraryVersions(entity.id, controller.signal)).items,
              ] as const,
          ),
        )
        if (controller.signal.aborted) return
        setEntities(entityPage.items)
        setVersions(Object.fromEntries(versionPages))
        setSnapshots(snapshotPage.items)
        setEntityId(entityPage.items[0]?.id ?? '')
        const approved = snapshotPage.items.find((snapshot) => snapshot.status === 'approved')
        setSnapshotId(approved?.id ?? '')
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load the Film Bible.')
        }
      })
    return () => controller.abort()
  }, [projectId])

  const selectedVersions = versions[entityId] ?? []
  const approvedVersions = selectedVersions.filter((version) => version.status === 'approved')
  const selectedSnapshot = snapshots.find((snapshot) => snapshot.id === snapshotId) ?? null
  const selectedShot = shots.find((shot) => shot.id === shotId) ?? null
  const entityNames = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity.display_name])),
    [entities],
  )

  function chooseEntity(nextEntityId: string) {
    setEntityId(nextEntityId)
    const firstApproved = (versions[nextEntityId] ?? []).find(
      (version) => version.status === 'approved',
    )
    setVersionId(firstApproved?.id ?? '')
  }

  function addPin() {
    const version = selectedVersions.find((item) => item.id === versionId)
    if (version?.status !== 'approved') return
    const next: FilmBiblePinSelection = {
      entity_id: entityId,
      version_id: version.id,
      role: roleForVersion[version.kind],
    }
    setDraftPins((current) => [
      ...current.filter((pin) => !(pin.entity_id === next.entity_id && pin.role === next.role)),
      next,
    ])
  }

  async function saveSnapshot() {
    if (draftPins.length === 0) return
    setPending(true)
    setMessage(null)
    try {
      const snapshot = await videoApi.createFilmBibleSnapshot(projectId, draftPins)
      setSnapshots((current) => [snapshot, ...current])
      setSnapshotId(snapshot.id)
      setMessage('Film Bible draft saved. Approve it before resolving names or binding shots.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to save the Film Bible draft.')
    } finally {
      setPending(false)
    }
  }

  async function approveSnapshot(id: string) {
    setPending(true)
    setMessage(null)
    try {
      const approved = await videoApi.approveFilmBibleSnapshot(projectId, id)
      setSnapshots((current) =>
        current.map((snapshot) => (snapshot.id === approved.id ? approved : snapshot)),
      )
      setSnapshotId(approved.id)
      setMessage('Film Bible approved. Its exact version pins are now available to shots.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to approve the Film Bible.')
    } finally {
      setPending(false)
    }
  }

  async function resolveMention() {
    if (selectedSnapshot?.status !== 'approved' || mention.trim() === '') return
    setPending(true)
    setMessage(null)
    try {
      setResolution(
        await videoApi.resolveFilmBibleName(projectId, selectedSnapshot.id, mention.trim()),
      )
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to resolve this name.')
    } finally {
      setPending(false)
    }
  }

  function toggleBinding(key: string) {
    setBindingKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    )
  }

  async function bindShot() {
    if (selectedShot === null || selectedSnapshot?.status !== 'approved') return
    const bindings = selectedSnapshot.pins
      .filter((pin) => bindingKeys.includes(pinKey(pin)))
      .map(selectionFor)
    if (bindings.length === 0) return
    setPending(true)
    setMessage(null)
    try {
      const revision = await videoApi.createShotBindingRevision(projectId, selectedShot.id, {
        shot_version: selectedShot.version,
        film_bible_snapshot_id: selectedSnapshot.id,
        bindings,
      })
      setMessage(
        `Shot binding revision ${String(revision.revision)} saved. References selected; continuity review is still required.`,
      )
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to bind this shot.')
    } finally {
      setPending(false)
    }
  }

  async function showAffected(pin: FilmBiblePin) {
    setPending(true)
    setMessage(null)
    try {
      const result = await videoApi.listAffectedShots(
        projectId,
        pin.entity_id,
        pin.library_version_id,
      )
      setAffected(
        result.shot_ids.length === 0
          ? 'No current shot bindings consume this version.'
          : `Affected shots: ${result.shot_ids.join(', ')}`,
      )
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to inspect affected shots.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="film-bible-editor" aria-labelledby="film-bible-title">
      <h3 id="film-bible-title">Project Film Bible</h3>
      <p>
        Pin approved identities, wardrobe, locations, props, and shot references. New library
        versions never replace these pins automatically.
      </p>
      {message === null ? null : <p role="status">{message}</p>}
      <div className="form-grid">
        <label className="field">
          <span>Library entity</span>
          <select value={entityId} onChange={(event) => chooseEntity(event.target.value)}>
            <option value="">Select an entity</option>
            {entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.display_name} · {entity.kind}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Approved version</span>
          <select value={versionId} onChange={(event) => setVersionId(event.target.value)}>
            <option value="">Select a version</option>
            {approvedVersions.map((version) => (
              <option key={version.id} value={version.id}>
                v{version.version_number} · {version.label} · {roleForVersion[version.kind]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        type="button"
        className="button button--secondary"
        disabled={versionId === ''}
        onClick={addPin}
      >
        Add or replace pin
      </button>
      <ul className="asset-list">
        {draftPins.map((pin) => (
          <li key={`${pin.entity_id}-${pin.role}`}>
            <strong>{entityNames.get(pin.entity_id) ?? pin.entity_id}</strong>
            <span>{pin.role}</span>
            <code>{pin.version_id}</code>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => setDraftPins((current) => current.filter((item) => item !== pin))}
            >
              Remove pin
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="button button--primary"
        disabled={pending || draftPins.length === 0}
        onClick={() => void saveSnapshot()}
      >
        {pending ? 'Working…' : 'Save Film Bible revision'}
      </button>

      <h4>Saved snapshots</h4>
      <ul className="asset-list">
        {snapshots.map((snapshot) => (
          <li key={snapshot.id}>
            <strong>
              Revision {snapshot.revision} · {snapshot.status}
            </strong>
            <span>{snapshot.pins.length} exact version pins</span>
            <code>{snapshot.fingerprint.slice(0, 16)}</code>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                setDraftPins(snapshot.pins.map(selectionFor))
                setMessage(
                  'Selective revision started. Replace only the intended pins, then save a new snapshot.',
                )
              }}
            >
              Start selective revision
            </button>
            {snapshot.status === 'draft' ? (
              <button
                type="button"
                className="button button--secondary"
                disabled={pending}
                onClick={() => void approveSnapshot(snapshot.id)}
              >
                Approve snapshot
              </button>
            ) : null}
            {snapshot.pins.map((pin) => (
              <button
                key={pinKey(pin)}
                type="button"
                className="button button--secondary"
                disabled={pending}
                onClick={() => void showAffected(pin)}
              >
                Check affected shots for {entityNames.get(pin.entity_id) ?? pin.entity_id} ·{' '}
                {pin.role}
              </button>
            ))}
          </li>
        ))}
      </ul>
      {affected === null ? null : <p role="status">{affected}</p>}

      <h4>Resolve a project mention</h4>
      <label className="field">
        <span>Approved snapshot</span>
        <select
          value={snapshotId}
          onChange={(event) => {
            setSnapshotId(event.target.value)
            setBindingKeys([])
          }}
        >
          <option value="">Select an approved snapshot</option>
          {snapshots
            .filter((snapshot) => snapshot.status === 'approved')
            .map((snapshot) => (
              <option key={snapshot.id} value={snapshot.id}>
                Revision {snapshot.revision}
              </option>
            ))}
        </select>
      </label>
      <label className="field">
        <span>Exact name or alias</span>
        <input value={mention} onChange={(event) => setMention(event.target.value)} />
      </label>
      <button
        type="button"
        className="button button--secondary"
        disabled={pending || selectedSnapshot?.status !== 'approved'}
        onClick={() => void resolveMention()}
      >
        Resolve mention
      </button>
      {resolution === null ? null : (
        <p role="status">
          {resolution.status}:{' '}
          {resolution.candidates.map((item) => item.display_name).join(', ') || 'no match'}
        </p>
      )}

      <h4>Bind approved pins to one shot</h4>
      <label className="field">
        <span>Shot</span>
        <select value={shotId} onChange={(event) => setShotId(event.target.value)}>
          <option value="">Select a shot</option>
          {shots.map((shot) => (
            <option key={shot.id} value={shot.id}>
              Shot {shot.draft.position + 1} · revision {shot.version}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="film-bible-pin-options" disabled={selectedSnapshot === null}>
        <legend>Exact pins consumed by this shot</legend>
        {selectedSnapshot?.pins.map((pin) => {
          const key = pinKey(pin)
          return (
            <label key={key}>
              <input
                type="checkbox"
                checked={bindingKeys.includes(key)}
                onChange={() => toggleBinding(key)}
              />
              {entityNames.get(pin.entity_id) ?? pin.entity_id} · {pin.role} · v
              {pin.library_version_number}
            </label>
          )
        })}
      </fieldset>
      <button
        type="button"
        className="button button--primary"
        disabled={pending || selectedShot === null || bindingKeys.length === 0}
        onClick={() => void bindShot()}
      >
        Save shot binding revision
      </button>
      <p className="film-warning">
        References selected is not a visual-consistency guarantee. Starting-frame approval and
        continuity review remain separate gates.
      </p>
    </section>
  )
}
