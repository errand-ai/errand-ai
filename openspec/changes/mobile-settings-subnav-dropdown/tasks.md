## Tasks

- [x] Create `frontend/src/components/settings/SettingsSectionPicker.vue` — props `sections: { id, label, to }[]` and `activeRoute: string`; emit `change(to)`; render closed-state button with current label + chevron; render floating panel with all sections on click; close on outside click or Escape; expose `aria-expanded`, listbox role; keyboard navigation (Up/Down/Enter/Esc).
- [x] Modify `frontend/src/pages/SettingsPage.vue` — extract the eight settings entries into a single `sections` array used by both layouts. Wrap the existing `<nav>` in `<div class="hidden sm:block">` (or equivalent). Add `<SettingsSectionPicker class="sm:hidden mb-4" :sections :active-route @change="to => router.push(to)" />` above the content panel. Drop `flex` shell on `< sm` so content takes full width.
- [x] Adjust `flex-1 min-w-0` content wrapper to render full-width when sidebar is hidden (apply `sm:flex-1` and unwrap from `flex` container at narrow widths, or use `flex-col sm:flex-row` on the parent).
- [x] Add vitest tests under `frontend/src/components/settings/__tests__/SettingsSectionPicker.spec.ts` — picker renders the active label, opens on click, emits `change` on selection, closes on Escape, supports keyboard navigation.
- [x] Add render test (or extend existing) for `SettingsPage.vue` — at narrow viewport (mock `matchMedia`), picker is mounted; at ≥640px, sidebar is mounted.
- [ ] Manual smoke: load `/settings/*` on a 375px viewport in Chrome devtools, verify content fills width, picker switches sections, mid-card layouts (textarea, profile cards) are still constrained as expected (their fix is out of scope).
- [x] Bump `VERSION` patch (0.121.5 → 0.121.6).
