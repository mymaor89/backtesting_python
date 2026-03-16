import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api'

export interface SavedPreset {
  id: number
  name: string
  tag: string
  category: string
  description: string
  state: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface PresetPayload {
  name: string
  tag: string
  category: string
  description: string
  state: Record<string, unknown>
}

export function usePresets() {
  const [presets, setPresets] = useState<SavedPreset[]>([])
  const [loading, setLoading] = useState(false)

  const fetchPresets = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/presets`)
      if (res.ok) {
        setPresets(await res.json())
      }
    } catch {
      // DB may be unavailable
    }
  }, [])

  useEffect(() => { fetchPresets() }, [fetchPresets])

  const savePreset = useCallback(async (payload: PresetPayload): Promise<SavedPreset | null> => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/presets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text)
      }
      const saved: SavedPreset = await res.json()
      setPresets(prev => [saved, ...prev])
      return saved
    } catch (e) {
      console.error('Failed to save preset:', e)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const updatePreset = useCallback(async (id: number, payload: PresetPayload): Promise<SavedPreset | null> => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/presets/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const updated: SavedPreset = await res.json()
      setPresets(prev => prev.map(p => p.id === id ? updated : p))
      return updated
    } catch (e) {
      console.error('Failed to update preset:', e)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const deletePreset = useCallback(async (id: number): Promise<boolean> => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/presets/${id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      setPresets(prev => prev.filter(p => p.id !== id))
      return true
    } catch (e) {
      console.error('Failed to delete preset:', e)
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  return { presets, loading, fetchPresets, savePreset, updatePreset, deletePreset }
}
