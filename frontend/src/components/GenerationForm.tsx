import { useMemo, useRef, useState, type RefObject, type SyntheticEvent } from 'react'

import type { GenerationRequest, ModelCapability } from '../api/contracts'
import { usePretextLayout } from '../hooks/usePretextLayout'

interface GenerationFormProps {
  models: ModelCapability[]
  isLoadingModels: boolean
  isSubmitting: boolean
  onSubmit: (request: GenerationRequest) => Promise<void>
}

function resolutionKey(width: number, height: number): string {
  return `${String(width)}x${String(height)}`
}

export function GenerationForm({
  models,
  isLoadingModels,
  isSubmitting,
  onSubmit,
}: GenerationFormProps) {
  const [prompt, setPrompt] = useState('')
  const [modelId, setModelId] = useState('')
  const [resolution, setResolution] = useState('')
  const [frameCount, setFrameCount] = useState('')
  const [seed, setSeed] = useState('')
  const [validationMessage, setValidationMessage] = useState<string | null>(null)
  const [invalidField, setInvalidField] = useState<string | null>(null)
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const modelRef = useRef<HTMLSelectElement>(null)
  const resolutionRef = useRef<HTMLSelectElement>(null)
  const frameCountRef = useRef<HTMLSelectElement>(null)
  const seedRef = useRef<HTMLInputElement>(null)

  const enabledModels = useMemo(() => models.filter((model) => model.enabled), [models])
  const selectedModel = enabledModels.find((model) => model.id === modelId)
  const introduction =
    'Describe the shot, choose a capability reported by the worker, and send it to the queue.'
  const introductionRef = usePretextLayout<HTMLParagraphElement>(introduction)

  const reject = (message: string, field: string, ref: RefObject<HTMLElement | null>): void => {
    setValidationMessage(message)
    setInvalidField(field)
    window.requestAnimationFrame(() => ref.current?.focus())
  }

  const handleModelChange = (nextModelId: string): void => {
    setModelId(nextModelId)
    setResolution('')
    setFrameCount('')
    setValidationMessage(null)
    setInvalidField(null)
  }

  const handleSubmit = async (event: SyntheticEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setValidationMessage(null)

    const normalizedPrompt = prompt.trim()
    if (normalizedPrompt.length === 0) {
      reject('Enter a prompt before generating.', 'prompt', promptRef)
      return
    }

    const capability = enabledModels.find((model) => model.id === modelId)
    const selectedResolution = capability?.resolutions.find(
      (item) => resolutionKey(item.width, item.height) === resolution,
    )
    const selectedFrameCount = Number(frameCount)
    if (
      capability === undefined ||
      selectedResolution === undefined ||
      !capability.frame_counts.includes(selectedFrameCount)
    ) {
      if (capability === undefined) {
        reject('Choose a model, resolution, and frame count.', 'model', modelRef)
      } else if (selectedResolution === undefined) {
        reject('Choose a model, resolution, and frame count.', 'resolution', resolutionRef)
      } else {
        reject('Choose a model, resolution, and frame count.', 'frame-count', frameCountRef)
      }
      return
    }

    const seedValue = seed.trim()
    let parsedSeed: number | null = null
    if (seedValue.length > 0) {
      if (!/^-?\d+$/u.test(seedValue)) {
        reject('Seed must be a whole number or left blank.', 'seed', seedRef)
        return
      }
      parsedSeed = Number(seedValue)
      if (!Number.isSafeInteger(parsedSeed)) {
        reject('Seed must be a safe whole number or left blank.', 'seed', seedRef)
        return
      }
    }

    const requestBase = {
      mode: 'text_to_video' as const,
      prompt: normalizedPrompt,
      model: capability.id,
      width: selectedResolution.width,
      height: selectedResolution.height,
      frame_count: selectedFrameCount,
    }
    const request: GenerationRequest =
      parsedSeed === null ? requestBase : { ...requestBase, seed: parsedSeed }

    await onSubmit(request)
  }

  const formReady =
    prompt.trim().length > 0 &&
    selectedModel !== undefined &&
    resolution.length > 0 &&
    frameCount.length > 0

  return (
    <section className="composer" aria-labelledby="composer-title">
      <div className="section-heading">
        <p className="eyebrow">Create</p>
        <h1 id="composer-title">New generation</h1>
        <p ref={introductionRef} className="section-heading__lede pretext-copy">
          {introduction}
        </p>
      </div>

      <form className="generation-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className="field field--prompt">
          <div className="field__header">
            <label htmlFor="prompt">Prompt</label>
            <span>{prompt.length} / 2,000</span>
          </div>
          <textarea
            ref={promptRef}
            id="prompt"
            name="prompt"
            value={prompt}
            maxLength={2_000}
            rows={7}
            placeholder="A slow tracking shot through a rain-soaked night market…"
            aria-invalid={invalidField === 'prompt'}
            aria-describedby={invalidField === 'prompt' ? 'form-validation-message' : undefined}
            onChange={(event) => {
              setPrompt(event.target.value)
              setValidationMessage(null)
              setInvalidField(null)
            }}
          />
        </div>

        <div className="field">
          <label htmlFor="model">Model</label>
          <select
            ref={modelRef}
            id="model"
            name="model"
            value={modelId}
            disabled={isLoadingModels || enabledModels.length === 0}
            aria-invalid={invalidField === 'model'}
            aria-describedby={invalidField === 'model' ? 'form-validation-message' : undefined}
            onChange={(event) => handleModelChange(event.target.value)}
          >
            <option value="">{isLoadingModels ? 'Loading capabilities…' : 'Choose a model'}</option>
            {enabledModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.display_name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="resolution">Resolution</label>
            <select
              ref={resolutionRef}
              id="resolution"
              name="resolution"
              value={resolution}
              disabled={selectedModel === undefined}
              aria-invalid={invalidField === 'resolution'}
              aria-describedby={
                invalidField === 'resolution' ? 'form-validation-message' : undefined
              }
              onChange={(event) => {
                setResolution(event.target.value)
                setValidationMessage(null)
                setInvalidField(null)
              }}
            >
              <option value="">Choose size</option>
              {selectedModel?.resolutions.map((item) => {
                const key = resolutionKey(item.width, item.height)
                return (
                  <option key={key} value={key}>
                    {item.width} × {item.height}
                  </option>
                )
              })}
            </select>
          </div>

          <div className="field">
            <label htmlFor="frame-count">Frames</label>
            <select
              ref={frameCountRef}
              id="frame-count"
              name="frame_count"
              value={frameCount}
              disabled={selectedModel === undefined}
              aria-invalid={invalidField === 'frame-count'}
              aria-describedby={
                invalidField === 'frame-count' ? 'form-validation-message' : undefined
              }
              onChange={(event) => {
                setFrameCount(event.target.value)
                setValidationMessage(null)
                setInvalidField(null)
              }}
            >
              <option value="">Choose frames</option>
              {selectedModel?.frame_counts.map((count) => (
                <option key={count} value={count}>
                  {count}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <div className="field__header">
            <label htmlFor="seed">Seed (optional)</label>
            <span>Blank = generated by server</span>
          </div>
          <input
            ref={seedRef}
            id="seed"
            name="seed"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={seed}
            placeholder="Random"
            aria-invalid={invalidField === 'seed'}
            aria-describedby={invalidField === 'seed' ? 'form-validation-message' : undefined}
            onChange={(event) => {
              setSeed(event.target.value)
              setValidationMessage(null)
              setInvalidField(null)
            }}
          />
        </div>

        {validationMessage === null ? null : (
          <p id="form-validation-message" className="form-message" role="alert">
            {validationMessage}
          </p>
        )}

        <button
          className="button button--primary button--generate"
          type="submit"
          disabled={!formReady || isSubmitting}
        >
          <span>{isSubmitting ? 'Sending to queue…' : 'Generate video'}</span>
          <span aria-hidden="true">↗</span>
        </button>
      </form>
    </section>
  )
}
