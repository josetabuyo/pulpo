import { describe, it, expect } from 'vitest'
import { isoToLocalInput, localInputToIso, localInputToMs } from './datetimeLocal'

describe('datetimeLocal', () => {
  it('round-trips a local input string through ISO and back', () => {
    const value = '2026-08-04T09:30'
    expect(isoToLocalInput(localInputToIso(value))).toBe(value)
  })

  it('converts a known UTC ISO string to the local input using the runner offset', () => {
    const iso = '2026-08-04T12:00:00.000Z'
    const d = new Date(iso)
    const offsetMs = d.getTimezoneOffset() * 60000
    const expected = new Date(d.getTime() - offsetMs).toISOString().slice(0, 16)
    expect(isoToLocalInput(iso)).toBe(expected)
  })

  it('returns empty string for falsy or invalid iso input', () => {
    expect(isoToLocalInput('')).toBe('')
    expect(isoToLocalInput(null)).toBe('')
    expect(isoToLocalInput('not-a-date')).toBe('')
  })

  it('returns null for empty or invalid local input value', () => {
    expect(localInputToIso('')).toBe(null)
    expect(localInputToIso(null)).toBe(null)
    expect(localInputToIso('not-a-date')).toBe(null)
    expect(localInputToMs('')).toBe(null)
    expect(localInputToMs('not-a-date')).toBe(null)
  })

  it('localInputToMs matches Date.parse of the local value', () => {
    const value = '2026-08-04T09:30'
    expect(localInputToMs(value)).toBe(new Date(value).getTime())
  })
})
