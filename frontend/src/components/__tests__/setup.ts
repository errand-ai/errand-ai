// Stub HTMLDialogElement methods not fully implemented in jsdom
if (typeof HTMLDialogElement !== 'undefined') {
  HTMLDialogElement.prototype.showModal ??= function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close ??= function () {
    this.removeAttribute('open')
  }
}
