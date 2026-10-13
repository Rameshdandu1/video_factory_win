import { type SyntheticEvent, useEffect, useMemo, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type {
  AssetKind,
  LibraryEntity,
  LibraryEntityKind,
  LibraryVersion,
  LibraryVersionKind,
  MediaAsset,
  ReferenceRole,
  RightsDeclaration,
} from '../api/contracts'

const entityKinds: { value: LibraryEntityKind; label: string }[] = [
  { value: 'character', label: 'Characters' },
  { value: 'location', label: 'Locations' },
  { value: 'prop', label: 'Props' },
  { value: 'shot_reference', label: 'Shot references' },
]

const versionKinds: Record<LibraryEntityKind, LibraryVersionKind[]> = {
  character: ['identity', 'wardrobe'],
  location: ['location_view', 'lighting_variant'],
  prop: ['prop_variant', 'prop_state'],
  shot_reference: ['shot_reference'],
}

const referenceRoles: ReferenceRole[] = [
  'identity_appearance',
  'location_or_prop',
  'source_layer',
  'starting_frame',
  'motion_performance',
  'shot_guidance',
  'review_only',
]

function defaultRole(kind: LibraryEntityKind): ReferenceRole {
  if (kind === 'character') return 'identity_appearance'
  if (kind === 'shot_reference') return 'shot_guidance'
  return 'location_or_prop'
}

function defaultVersionKind(kind: LibraryEntityKind): LibraryVersionKind {
  if (kind === 'character') return 'identity'
  if (kind === 'location') return 'location_view'
  if (kind === 'prop') return 'prop_variant'
  return 'shot_reference'
}

interface SelectedAsset {
  role: ReferenceRole
  viewLabel: string
}

export function FilmLibraryView() {
  const [kind, setKind] = useState<LibraryEntityKind>('character')
  const [entities, setEntities] = useState<LibraryEntity[]>([])
  const [assets, setAssets] = useState<MediaAsset[]>([])
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null)
  const [versions, setVersions] = useState<LibraryVersion[]>([])
  const [displayName, setDisplayName] = useState('')
  const [aliases, setAliases] = useState('')
  const [search, setSearch] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [assetKind, setAssetKind] = useState<AssetKind>('image')
  const [rights, setRights] = useState<RightsDeclaration>('permissioned')
  const [selectedAssets, setSelectedAssets] = useState<Record<string, SelectedAsset>>({})
  const [versionKind, setVersionKind] = useState<LibraryVersionKind>('identity')
  const [versionLabel, setVersionLabel] = useState('')
  const [notes, setNotes] = useState('')
  const [invariants, setInvariants] = useState('')
  const [stateNotes, setStateNotes] = useState('')
  const [rightsStatement, setRightsStatement] = useState('')
  const [voiceProfileId, setVoiceProfileId] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const selectedEntity = useMemo(
    () => entities.find((entity) => entity.id === selectedEntityId) ?? null,
    [entities, selectedEntityId],
  )

  async function refresh(activeKind = kind, activeSearch = search) {
    const [entityPage, assetPage] = await Promise.all([
      videoApi.listLibraryEntities(activeKind, activeSearch),
      videoApi.listLibraryAssets(),
    ])
    setEntities(entityPage.items)
    setAssets(assetPage.items)
    if (
      selectedEntityId !== null &&
      !entityPage.items.some((entity) => entity.id === selectedEntityId)
    ) {
      setSelectedEntityId(null)
      setVersions([])
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([
      videoApi.listLibraryEntities(kind, undefined, controller.signal),
      videoApi.listLibraryAssets(controller.signal),
    ])
      .then(([entityPage, assetPage]) => {
        setEntities(entityPage.items)
        setAssets(assetPage.items)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load the film library.')
        }
      })
    return () => controller.abort()
  }, [kind])

  async function createEntity(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setMessage(null)
    try {
      const entity = await videoApi.createLibraryEntity({
        kind,
        display_name: displayName.trim(),
        aliases: aliases
          .split(',')
          .map((alias) => alias.trim())
          .filter(Boolean),
      })
      setEntities((current) => [entity, ...current])
      setDisplayName('')
      setAliases('')
      await selectEntity(entity)
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to create the library item.')
    } finally {
      setPending(false)
    }
  }

  async function uploadAsset(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    if (file === null) return
    setPending(true)
    setMessage(null)
    try {
      const asset = await videoApi.uploadLibraryAsset(file, assetKind, rights)
      setAssets((current) => [asset, ...current])
      setFile(null)
      setMessage('Reusable source uploaded. Create a version to define how it may be used.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to upload the source asset.')
    } finally {
      setPending(false)
    }
  }

  async function selectEntity(entity: LibraryEntity) {
    setSelectedEntityId(entity.id)
    setVersionKind(defaultVersionKind(entity.kind))
    setSelectedAssets({})
    setMessage(null)
    try {
      const page = await videoApi.listLibraryVersions(entity.id)
      setVersions(page.items)
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to load library versions.')
    }
  }

  async function inspectAsset(asset: MediaAsset) {
    setPending(true)
    setMessage(null)
    try {
      const inspected = await videoApi.inspectLibraryAsset(asset.id)
      setAssets((current) => current.map((item) => (item.id === inspected.id ? inspected : item)))
      setMessage('Verified media metadata recorded as a new immutable asset version.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to inspect this source asset.')
    } finally {
      setPending(false)
    }
  }

  function toggleAsset(assetId: string, checked: boolean) {
    setSelectedAssets((current) => {
      if (!checked) {
        return Object.fromEntries(Object.entries(current).filter(([key]) => key !== assetId))
      }
      return {
        ...current,
        [assetId]: { role: defaultRole(selectedEntity?.kind ?? kind), viewLabel: '' },
      }
    })
  }

  async function createVersion(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    if (selectedEntity === null) return
    setPending(true)
    setMessage(null)
    try {
      const version = await videoApi.createLibraryVersion(selectedEntity.id, {
        kind: versionKind,
        label: versionLabel.trim(),
        notes,
        invariants,
        state_notes: stateNotes,
        voice_profile_id: voiceProfileId.trim() || null,
        rights_statement: rightsStatement,
        assets: Object.entries(selectedAssets).map(([assetId, selection]) => ({
          asset_id: assetId,
          role: selection.role,
          view_label: selection.viewLabel.trim() || null,
        })),
      })
      setVersions((current) => [version, ...current])
      setVersionLabel('')
      setSelectedAssets({})
      setMessage('Draft version saved with exact asset hashes and roles.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to create the version.')
    } finally {
      setPending(false)
    }
  }

  async function approveVersion(version: LibraryVersion) {
    if (selectedEntity === null) return
    setPending(true)
    setMessage(null)
    try {
      const approved = await videoApi.approveLibraryVersion(selectedEntity.id, version.id)
      setVersions((current) => current.map((item) => (item.id === approved.id ? approved : item)))
      setMessage('Version approved. Later project pinning will use this immutable snapshot.')
    } catch (error: unknown) {
      setMessage(isApiClientError(error) ? error.message : 'Unable to approve the version.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main id="workspace" className="projects-workspace library-workspace">
      <section className="project-create" aria-labelledby="library-create-title">
        <p className="eyebrow">Reusable source library</p>
        <h1 id="library-create-title">Film Library</h1>
        <p className="project-cost-label">
          Names are labels. Approved versions preserve exact source hashes; visual identity still
          requires human review.
        </p>
        <div className="library-tabs" role="tablist" aria-label="Library category">
          {entityKinds.map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={kind === item.value}
              onClick={() => {
                setKind(item.value)
                setSelectedEntityId(null)
                setVersions([])
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        <form onSubmit={(event) => void createEntity(event)}>
          <label className="field">
            <span>Name</span>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              required
              maxLength={200}
              placeholder={kind === 'character' ? 'Arjun / అర్జున్' : 'Village Temple'}
            />
          </label>
          <label className="field">
            <span>Aliases (comma separated)</span>
            <input value={aliases} onChange={(event) => setAliases(event.target.value)} />
          </label>
          <button className="button button--primary" disabled={pending || !displayName.trim()}>
            Create library item
          </button>
        </form>

        <form onSubmit={(event) => void uploadAsset(event)} className="asset-manager">
          <h2>Upload reusable source</h2>
          <label className="field">
            <span>Media file</span>
            <input
              type="file"
              accept="image/png,image/jpeg,video/mp4,audio/wav"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div className="form-grid">
            <label className="field">
              <span>Media kind</span>
              <select
                value={assetKind}
                onChange={(event) => setAssetKind(event.target.value as AssetKind)}
              >
                <option value="image">Image</option>
                <option value="video">Video</option>
                <option value="audio">Audio</option>
              </select>
            </label>
            <label className="field">
              <span>Rights declaration</span>
              <select
                value={rights}
                onChange={(event) => setRights(event.target.value as RightsDeclaration)}
              >
                <option value="permissioned">Permissioned</option>
                <option value="owned">Owned</option>
                <option value="licensed">Licensed</option>
                <option value="public_domain">Public domain</option>
              </select>
            </label>
          </div>
          <button className="button button--secondary" disabled={pending || file === null}>
            Upload source
          </button>
        </form>
        {message === null ? null : (
          <p className="project-message" role="status">
            {message}
          </p>
        )}
      </section>

      <section className="project-list" aria-labelledby="library-items-title">
        <p className="eyebrow">Owner-scoped and reusable</p>
        <h2 id="library-items-title">Saved items</h2>
        <label className="field">
          <span>Search English or Telugu names and aliases</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void refresh()
              }
            }}
          />
        </label>
        <ul>
          {entities.map((entity) => (
            <li key={entity.id}>
              <button type="button" onClick={() => void selectEntity(entity)}>
                <strong>{entity.display_name}</strong>
                <span>{entity.aliases.join(' · ') || 'No aliases'}</span>
                <span>Metadata v{entity.metadata_version}</span>
              </button>
            </li>
          ))}
        </ul>

        {selectedEntity === null ? null : (
          <div className="film-editor">
            <h2>{selectedEntity.display_name}: immutable versions</h2>
            <form onSubmit={(event) => void createVersion(event)}>
              <div className="form-grid">
                <label className="field">
                  <span>Version type</span>
                  <select
                    value={versionKind}
                    onChange={(event) => setVersionKind(event.target.value as LibraryVersionKind)}
                  >
                    {versionKinds[selectedEntity.kind].map((item) => (
                      <option key={item} value={item}>
                        {item.replaceAll('_', ' ')}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Version label</span>
                  <input
                    value={versionLabel}
                    onChange={(event) => setVersionLabel(event.target.value)}
                    required
                    placeholder="Blue shirt identity pack"
                  />
                </label>
              </div>
              <label className="field">
                <span>Invariants (features that should remain stable)</span>
                <textarea
                  value={invariants}
                  onChange={(event) => setInvariants(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Appearance / architecture notes</span>
                <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
              </label>
              <label className="field">
                <span>Variant or story-state notes</span>
                <textarea
                  value={stateNotes}
                  onChange={(event) => setStateNotes(event.target.value)}
                />
              </label>
              {selectedEntity.kind === 'character' ? (
                <label className="field">
                  <span>Optional voice-profile ID</span>
                  <input
                    value={voiceProfileId}
                    onChange={(event) => setVoiceProfileId(event.target.value)}
                  />
                </label>
              ) : null}
              <label className="field">
                <span>Rights / consent notes</span>
                <textarea
                  value={rightsStatement}
                  onChange={(event) => setRightsStatement(event.target.value)}
                />
              </label>
              <fieldset className="library-bindings">
                <legend>Exact source bindings and roles</legend>
                {assets.map((asset) => {
                  const selection = selectedAssets[asset.id]
                  return (
                    <div key={asset.id} className="library-binding">
                      <label className="checkbox-field">
                        <input
                          type="checkbox"
                          disabled={asset.kind !== 'image' && asset.state !== 'inspected'}
                          checked={selection !== undefined}
                          onChange={(event) => toggleAsset(asset.id, event.target.checked)}
                        />
                        <span>
                          {asset.original_filename} · {asset.kind} · SHA {asset.sha256.slice(0, 12)}
                          …
                        </span>
                      </label>
                      {asset.state === 'ready' && asset.kind !== 'image' ? (
                        <button
                          type="button"
                          className="button button--secondary"
                          disabled={pending}
                          onClick={() => void inspectAsset(asset)}
                        >
                          Verify media metadata
                        </button>
                      ) : asset.state === 'inspected' ? (
                        <span>
                          Inspected · {String(asset.metadata?.duration_ms ?? 0)} ms · v
                          {asset.version}
                        </span>
                      ) : null}
                      {selection === undefined ? null : (
                        <div className="form-grid">
                          <label className="field">
                            <span>Reference role</span>
                            <select
                              value={selection.role}
                              onChange={(event) =>
                                setSelectedAssets((current) => ({
                                  ...current,
                                  [asset.id]: {
                                    ...selection,
                                    role: event.target.value as ReferenceRole,
                                  },
                                }))
                              }
                            >
                              {referenceRoles.map((role) => (
                                <option key={role} value={role}>
                                  {role.replaceAll('_', ' ')}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="field">
                            <span>View label (optional)</span>
                            <input
                              value={selection.viewLabel}
                              onChange={(event) =>
                                setSelectedAssets((current) => ({
                                  ...current,
                                  [asset.id]: { ...selection, viewLabel: event.target.value },
                                }))
                              }
                              placeholder="front, profile, courtyard"
                            />
                          </label>
                        </div>
                      )}
                    </div>
                  )
                })}
              </fieldset>
              <button
                className="button button--primary"
                disabled={pending || !versionLabel.trim() || !Object.keys(selectedAssets).length}
              >
                Save immutable draft version
              </button>
            </form>

            <ul className="asset-list">
              {versions.map((version) => (
                <li key={version.id}>
                  <strong>
                    v{version.version_number} · {version.label}
                  </strong>
                  <span>
                    {version.kind.replaceAll('_', ' ')} · {version.status} · {version.assets.length}{' '}
                    exact source binding(s)
                  </span>
                  <code>{version.fingerprint}</code>
                  {version.status === 'draft' ? (
                    <button
                      className="button button--secondary"
                      type="button"
                      disabled={pending}
                      onClick={() => void approveVersion(version)}
                    >
                      Approve version
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  )
}
