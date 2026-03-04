// Stub HTMLDialogElement methods not fully implemented in jsdom
if (typeof HTMLDialogElement !== 'undefined') {
  HTMLDialogElement.prototype.showModal ??= function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close ??= function () {
    this.removeAttribute('open')
  }
}

// Mock EventSource (not available in jsdom)
class MockEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  readonly CONNECTING = 0
  readonly OPEN = 1
  readonly CLOSED = 2
  url: string
  readyState = 0
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(url: string | URL) {
    this.url = url.toString()
  }

  addEventListener() {}
  removeEventListener() {}
  dispatchEvent() { return true }
  close() { this.readyState = 2 }
}

if (typeof globalThis.EventSource === 'undefined') {
  (globalThis as unknown as Record<string, unknown>).EventSource = MockEventSource
}

// Mock matchMedia (not available in jsdom, used by HeaderBar's useResponsive)
// Return matches: true to simulate a desktop viewport (min-width queries pass)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})
