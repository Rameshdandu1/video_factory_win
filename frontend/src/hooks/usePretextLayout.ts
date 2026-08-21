import { layout, prepare } from '@chenglou/pretext'
import { useEffect, useRef, type RefObject } from 'react'

function numericLineHeight(element: HTMLElement): number {
  const styles = getComputedStyle(element)
  const parsed = Number.parseFloat(styles.lineHeight)
  if (Number.isFinite(parsed)) {
    return parsed
  }
  return Number.parseFloat(styles.fontSize) * 1.45
}

/**
 * Uses Pretext's prepared text handle to keep dynamic copy blocks correctly sized
 * without forcing repeated browser measurement during responsive relayout.
 */
export function usePretextLayout<T extends HTMLElement>(text: string): RefObject<T | null> {
  const elementRef = useRef<T>(null)

  useEffect(() => {
    const element = elementRef.current
    if (element === null || typeof ResizeObserver === 'undefined') {
      return undefined
    }

    let disposed = false
    let observer: ResizeObserver | null = null
    let frameId: number | null = null
    let measuredWidth = -1

    const prepareLayout = async (): Promise<void> => {
      if ('fonts' in document) {
        await document.fonts.ready
      }
      if (disposed) {
        return
      }

      try {
        const styles = getComputedStyle(element)
        const prepared = prepare(text, styles.font, {
          letterSpacing: Number.parseFloat(styles.letterSpacing) || 0,
        })
        const relayout = (): void => {
          frameId = null
          const width = element.clientWidth
          if (disposed || width <= 0 || width === measuredWidth) {
            return
          }
          measuredWidth = width
          try {
            const result = layout(prepared, width, numericLineHeight(element))
            const nextHeight = `${String(Math.ceil(result.height))}px`
            if (element.style.getPropertyValue('--pretext-height') !== nextHeight) {
              element.style.setProperty('--pretext-height', nextHeight)
            }
          } catch {
            observer?.disconnect()
            observer = null
          }
        }
        const scheduleRelayout = (): void => {
          if (disposed || frameId !== null) {
            return
          }
          frameId = window.requestAnimationFrame(relayout)
        }

        observer = new ResizeObserver(scheduleRelayout)
        observer.observe(element)
        scheduleRelayout()
      } catch {
        // Native CSS remains the safe fallback when measurement is unavailable.
      }
    }

    void prepareLayout()
    return () => {
      disposed = true
      observer?.disconnect()
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId)
      }
      element.style.removeProperty('--pretext-height')
    }
  }, [text])

  return elementRef
}
