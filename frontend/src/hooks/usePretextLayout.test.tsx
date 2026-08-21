import { act, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pretext = vi.hoisted(() => ({
  layout: vi.fn(() => ({ height: 47.2 })),
  prepare: vi.fn(() => ({ prepared: true })),
}))

vi.mock('@chenglou/pretext', () => pretext)

import { usePretextLayout } from './usePretextLayout'

function Harness() {
  const ref = usePretextLayout<HTMLParagraphElement>('Measured copy')
  return <p ref={ref}>Measured copy</p>
}

describe('usePretextLayout', () => {
  let observerCallback: ResizeObserverCallback | null
  let width: number
  let nextFrameId: number
  let frames: Map<number, FrameRequestCallback>
  const observe = vi.fn()
  const disconnect = vi.fn()

  beforeEach(() => {
    observerCallback = null
    width = 320
    nextFrameId = 0
    frames = new Map()
    observe.mockReset()
    disconnect.mockReset()
    pretext.layout.mockClear()
    pretext.prepare.mockClear()

    class TestResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCallback = callback
      }

      observe = observe
      disconnect = disconnect
      unobserve = vi.fn()
    }

    vi.stubGlobal('ResizeObserver', TestResizeObserver)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      nextFrameId += 1
      frames.set(nextFrameId, callback)
      return nextFrameId
    })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((frameId) => {
      frames.delete(frameId)
    })
  })

  const flushFrames = (): void => {
    const pending = [...frames.values()]
    frames.clear()
    for (const callback of pending) {
      callback(0)
    }
  }

  it('coalesces resize notifications and writes only when the measured width changes', () => {
    const view = render(<Harness />)
    const paragraph = view.getByText('Measured copy')

    act(flushFrames)
    expect(pretext.layout).toHaveBeenCalledTimes(1)
    expect(paragraph).toHaveStyle({ '--pretext-height': '48px' })

    const notify = observerCallback
    if (notify === null) {
      throw new Error('expected ResizeObserver callback')
    }
    act(() => {
      notify([], {} as ResizeObserver)
      notify([], {} as ResizeObserver)
      flushFrames()
    })
    expect(pretext.layout).toHaveBeenCalledTimes(1)

    width = 480
    act(() => {
      notify([], {} as ResizeObserver)
      flushFrames()
    })
    expect(pretext.layout).toHaveBeenCalledTimes(2)

    act(() => notify([], {} as ResizeObserver))
    view.unmount()
    expect(disconnect).toHaveBeenCalledTimes(1)
    expect(frames.size).toBe(0)
  })
})
