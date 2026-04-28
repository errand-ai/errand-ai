"""Provider name canonicalization for WebSocket OAuth flows.

The errand server's internal naming for the Google integration is
`google_drive` (DB platform_id, HTTP path param, settings UI keys).
errand-cloud was updated 2026-04-27 to use the canonical name
`google_workspace` over the WebSocket relay (with `google_drive` retained as a
deprecated alias). To stay correct on both sides without forcing a DB
migration, we translate at the WebSocket boundary:

    internal `google_drive`  <->  canonical `google_workspace` (on the wire)

Other providers (e.g. `onedrive`) pass through unchanged.

Kept in a tiny standalone module so low-level utilities like
`cloud_storage.py` and `cloud_client.py` can import the mapping without
pulling in the FastAPI routes module.
"""

_WIRE_NAME_FOR_INTERNAL = {"google_drive": "google_workspace"}
_INTERNAL_NAME_FOR_WIRE = {"google_workspace": "google_drive"}


def to_wire_provider(internal: str) -> str:
    """Map an internal provider name to the canonical name used on the WebSocket."""
    return _WIRE_NAME_FOR_INTERNAL.get(internal, internal)


def from_wire_provider(wire: str) -> str:
    """Map a wire (canonical or alias) provider name to the internal name.

    Accepts both the canonical name (`google_workspace`) and the deprecated
    alias (`google_drive`) for backwards compatibility with older cloud
    deployments.
    """
    return _INTERNAL_NAME_FOR_WIRE.get(wire, wire)
