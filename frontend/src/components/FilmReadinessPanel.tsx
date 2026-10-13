import { useEffect, useState } from 'react'

import { isApiClientError, videoApi } from '../api/client'
import type { FilmReadiness } from '../api/contracts'

interface FilmReadinessPanelProps {
  projectId: string
  refreshToken: string
}

function label(value: string): string {
  return value.replaceAll('_', ' ')
}

export function FilmReadinessPanel({ projectId, refreshToken }: FilmReadinessPanelProps) {
  const [readiness, setReadiness] = useState<FilmReadiness | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void videoApi
      .getFilmReadiness(projectId, controller.signal)
      .then((current) => {
        setReadiness(current)
        setMessage(null)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(isApiClientError(error) ? error.message : 'Unable to load film readiness.')
        }
      })
    return () => controller.abort()
  }, [projectId, refreshToken])

  return (
    <section className="film-readiness-panel" aria-labelledby="film-readiness-heading">
      <div>
        <p className="eyebrow">Phase 7B</p>
        <h4 id="film-readiness-heading">Continuity and acceptance readiness</h4>
        <p>
          Derived from current persisted revisions after every load. Reviewers still judge the real
          media; this panel never infers film quality from duration.
        </p>
      </div>
      {readiness === null ? (
        <p role="status">{message ?? 'Checking current gates…'}</p>
      ) : (
        <>
          <div className="film-gate-summary">
            <span>{readiness.accepted ? 'Acceptance complete' : 'Acceptance incomplete'}</span>
            <span>
              {readiness.next_gate === null
                ? 'No project gate is actionable'
                : `Next gate: ${label(readiness.next_gate)}`}
            </span>
            <span>{`${String(readiness.continuity_boundaries.length)} shot boundaries`}</span>
            <span>{`${String(readiness.pending_approvals.length)} current approvals pending`}</span>
          </div>
          {readiness.structural_blockers.length === 0 ? (
            <p className="readiness-ok">Scene and shot timing covers the 900-second contract.</p>
          ) : (
            <div className="film-warning">
              <strong>Structural blockers</strong>
              <ul>
                {readiness.structural_blockers.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="readiness-grid" aria-label="Film gate readiness">
            <span data-ready={readiness.ready_for_rough_cut}>Rough cut</span>
            <span data-ready={readiness.ready_for_final_footage}>Final footage</span>
            <span data-ready={readiness.ready_for_dialogue_90_seconds}>90-second review</span>
            <span data-ready={readiness.ready_for_sequence_180_seconds}>3-minute review</span>
            <span data-ready={readiness.ready_for_film_900_seconds}>15-minute review</span>
            <span data-ready={readiness.ready_for_final_sound}>Final sound</span>
          </div>
          <details>
            <summary>Pending current approvals ({readiness.pending_approvals.length})</summary>
            {readiness.pending_approvals.length === 0 ? (
              <p>No fingerprint-bound approvals are pending.</p>
            ) : (
              <ul className="readiness-list">
                {readiness.pending_approvals.map((item, index) => (
                  <li
                    key={`${item.stage}:${item.scene_id ?? ''}:${item.shot_id ?? ''}:${String(index)}`}
                  >
                    <strong>{label(item.stage)}</strong>
                    <span>{item.message}</span>
                    {item.shot_id === null ? null : <code>{item.shot_id}</code>}
                    {item.shot_id !== null || item.scene_id === null ? null : (
                      <code>{item.scene_id}</code>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </details>
          <details>
            <summary>
              Adjacent-shot continuity ({readiness.continuity_boundaries.length} boundaries)
            </summary>
            {readiness.continuity_boundaries.length === 0 ? (
              <p>Add at least two ordered shots to create a continuity boundary.</p>
            ) : (
              <ol className="readiness-list">
                {readiness.continuity_boundaries.map((boundary) => (
                  <li key={boundary.fingerprint}>
                    <strong>{`${boundary.left_shot_id} → ${boundary.right_shot_id}`}</strong>
                    <span>
                      {boundary.cross_scene ? 'Cross-scene boundary' : 'Same-scene boundary'}
                    </span>
                    <span>
                      {boundary.changed_fields.length === 0
                        ? 'No structured scene-field changes.'
                        : `Review changes: ${boundary.changed_fields.map(label).join(', ')}`}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </details>
        </>
      )}
    </section>
  )
}
