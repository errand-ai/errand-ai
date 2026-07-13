import { useAuthStore } from '../stores/auth'

/**
 * Shared helpers for the settings cards/pages that self-load their own state.
 *
 * After Wave 2 the Settings page no longer `provide()`s a shared `settings-state`
 * object; each remaining server-admin section (Git SSH key, MCP API key, plugin
 * poll interval, OIDC config) loads and saves its own slice of `/api/settings`.
 * This composable centralises the auth-aware GET/PUT and the metadata `extractValue`
 * helper so those consumers share one implementation rather than duplicating it.
 */

/** `/api/settings` returns each key as `{ value, source, sensitive, readonly }`. */
export interface SettingEntry {
  value: any
  source: string
  sensitive: boolean
  readonly: boolean
}

export type SettingsMetadata = Record<string, SettingEntry>

export function useSettingsApi() {
  const auth = useAuthStore()

  async function settingsFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
      ...((options.headers as Record<string, string>) || {}),
    }
    if (auth.token) {
      headers['Authorization'] = `Bearer ${auth.token}`
    }
    return fetch(url, { ...options, headers })
  }

  /** Load the full `/api/settings` payload (metadata format). Throws on non-OK. */
  async function loadSettings(): Promise<Record<string, any>> {
    const res = await settingsFetch('/api/settings')
    if (res.status === 403) throw new Error('Access denied — admin role required.')
    if (!res.ok) throw new Error(`Failed to load settings (HTTP ${res.status})`)
    return res.json()
  }

  /** PUT a partial settings update. Mirrors the pre-Wave-2 `saveSettings` semantics. */
  async function saveSettings(data: Record<string, unknown>): Promise<void> {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (res.status === 403) throw new Error('Access denied — admin role required.')
    if (!res.ok) throw new Error(`Failed to save settings (HTTP ${res.status})`)
  }

  return { settingsFetch, loadSettings, saveSettings }
}

/**
 * Read a value from an `/api/settings` payload, tolerating both the metadata
 * format (`{ value, ... }`) and a plain-value format for backwards compat.
 */
export function extractSettingValue(data: Record<string, any>, key: string, fallback: any = ''): any {
  const entry = data[key]
  if (entry && typeof entry === 'object' && 'value' in entry) {
    return entry.value ?? fallback
  }
  return entry ?? fallback
}
