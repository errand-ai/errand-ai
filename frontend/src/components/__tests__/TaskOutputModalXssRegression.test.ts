/**
 * Regression test for GHSA-h8r8-wccr-v5f2 (mutation-XSS re-contextualisation
 * class in DOMPurify < 3.3.2 with the default config).
 *
 * This test exercises `TaskOutputModal` as imported from
 * `@errand-ai/ui-components` (i.e. through the real dep chain this repo bumps
 * in the `fix-dependabot-alerts` change), not a locally-stubbed replacement.
 * It renders payloads known to trigger the pre-3.3.2 mutation-XSS class and
 * asserts the browser-parsed DOM contains no executable script context and
 * no `on*` event-handler attributes that could be attributed to the payload.
 *
 * See:
 * - openspec/changes/fix-dependabot-alerts/specs/task-output-viewer/spec.md
 *   ("Scenario: Mutation-XSS payload class is neutralised")
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { TaskOutputModal } from '@errand-ai/ui-components'

// Payload class from GHSA-h8r8-wccr-v5f2: template re-parse mutation-XSS.
// Pre-3.3.2 dompurify (default config) could allow these to surface an
// `<img onerror=...>` or similar after the browser re-parsed the sanitised
// output into a foreign / template context.
const MUTATION_XSS_PAYLOADS: ReadonlyArray<string> = [
  '<math><mtext><table><mglyph><style><!--</style><img src onerror=alert(1)>',
  '<svg><p><style><g title="</style><img src=x onerror=alert(1)>">',
  '<form><math><mtext></form><form><mglyph><style></math><img src onerror=alert(1)>',
  '<form><math><mtext></form><form><mglyph><svg><mtext><textarea><a title="</textarea><img src=x onerror=alert(1)>">',
]

describe('TaskOutputModal — mutation-XSS payload class is neutralised', () => {
  for (const payload of MUTATION_XSS_PAYLOADS) {
    it(`neutralises payload: ${payload.slice(0, 48)}…`, () => {
      const wrapper = mount(TaskOutputModal, {
        props: { title: 'XSS regression', output: payload },
      })

      // The rendered-output container holds the sanitised, payload-derived DOM.
      // Benign template chrome (header/footer) does not contain <img>, <script>,
      // or event handlers, so any occurrence inside this node would be
      // attributable to the payload.
      const outputContainer = wrapper.find('.prose').element as HTMLElement

      // Assertion 1: no <script> elements survived sanitisation.
      expect(outputContainer.querySelectorAll('script').length).toBe(0)

      // Assertion 2: no on* event-handler attributes on any rendered element.
      const allElements = outputContainer.querySelectorAll('*')
      for (const el of Array.from(allElements)) {
        for (const attr of Array.from(el.attributes)) {
          expect(attr.name.toLowerCase()).not.toMatch(/^on/)
        }
      }

      // Assertion 3: no dangerous-scheme URLs attributable to the payload.
      // Covers javascript:, data:, and vbscript: — the URL-scheme XSS vectors
      // DOMPurify is expected to neutralise.
      const html = outputContainer.innerHTML.toLowerCase()
      const dangerousSchemes = ['javascript:', 'data:', 'vbscript:']
      for (const scheme of dangerousSchemes) {
        expect(html).not.toContain(scheme)
      }

      // Assertion 4: any surviving <img> elements have no executable URL vectors
      // (onerror/onload/etc. are covered by assertion 2, but re-check that
      // src is not a dangerous-scheme URL — belt and braces).
      for (const img of Array.from(outputContainer.querySelectorAll('img'))) {
        const src = (img.getAttribute('src') ?? '').toLowerCase().trim()
        for (const scheme of dangerousSchemes) {
          expect(src.startsWith(scheme)).toBe(false)
        }
      }
    })
  }
})
