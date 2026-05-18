## Approach

Use Tailwind's responsive utilities to swap rendering between a sidebar (current) and a dropdown picker. The two render trees do not coexist visually — only one is mounted at a time, controlled by `@media (min-width: 640px)` via Tailwind's `sm:` prefix.

```
< 640px                              ≥ 640px
┌──────────────────────────────┐     ┌────────────────────────────────────┐
│ Settings                     │     │ Settings                           │
│                              │     │                                    │
│ ┌─ Section ▾ ──────────────┐ │     │ ┌─ nav ──┐  ┌─ content ─────────┐  │
│ │ Task Profiles            │ │     │ │ Agent  │  │  ...              │  │
│ └──────────────────────────┘ │     │ │ Tasks  │  │                   │  │
│                              │     │ │▸Profil.│  │                   │  │
│ ┌─ content ────────────────┐ │     │ │ ...    │  │                   │  │
│ │  ...                     │ │     │ └────────┘  └───────────────────┘  │
│ └──────────────────────────┘ │     │                                    │
└──────────────────────────────┘     └────────────────────────────────────┘
```

## Component shape

```
frontend/src/components/settings/SettingsSectionPicker.vue
  Props: sections: { id, label, to }[], activeRoute: string
  Emits: change(to: string)
  Renders: closed-state button showing current section + chevron
           open-state floating panel listing all sections
  A11y:    aria-expanded, listbox role, keyboard nav (Up/Down/Enter/Esc)
```

## Decisions

- **Custom dropdown, not native `<select>`.** Future phases want capability badges, descriptions, and visual continuity with `HeaderBar`'s burger menu. Even at this stage, a styled component is a small addition that pre-empts a re-do later.
- **Local to errand UI for now.** Could go in the library, but the *real* picker (with capability awareness) will be designed in Phase 1. Adding it locally keeps this PR self-contained.
- **No router refactor.** The component emits `change` and the parent calls `router.push`. The existing nested-route layout remains untouched.
- **Breakpoint = `sm` (640px).** Matches `useResponsive()` in the shared library so Phase 1 can replace this without a breakpoint shift.

## What's NOT changing in this phase

- Card internal layouts (textareas, profile cards) — addressed alongside Phase 1 library migration.
- The 17 settings cards' file locations or exports.
- Any backend or capability advertisement.
