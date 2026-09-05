"""A catalog of known hosted LLM providers, so adding one is a choice not a URL.

Every base URL here was verified against the live endpoint: an unauthenticated
``GET {base_url}/models`` answering 200, 401 or 403 proves the endpoint exists;
404 or a DNS failure proves the entry wrong. Re-verify when editing this file —
`openspec/changes/local-ai-provider-detection/design.md` records the method and
the codes observed.

The catalog is a convenience, never a gate: the final entry takes a
caller-supplied base URL, so a provider absent from this list is one form field
away rather than unreachable. That is also why catalog rot degrades rather than
blocks.
"""

from dataclasses import dataclass

# The escape hatch: an OpenAI-compatible provider this catalog does not list.
OTHER_ENTRY_ID = "other"


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    display_name: str
    base_url: str | None
    supports_model_listing: bool
    api_key_url: str | None = None
    requires_base_url: bool = False
    note: str | None = None


PROVIDER_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        id="openrouter",
        display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        supports_model_listing=True,
        api_key_url="https://openrouter.ai/keys",
        note="Aggregator covering many providers behind one key. Chat completions only — it exposes no embeddings endpoint.",
    ),
    CatalogEntry(
        id="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        supports_model_listing=True,
        api_key_url="https://platform.openai.com/api-keys",
    ),
    CatalogEntry(
        id="anthropic",
        display_name="Anthropic",
        base_url="https://api.anthropic.com/v1",
        supports_model_listing=True,
        api_key_url="https://console.anthropic.com/settings/keys",
        note="OpenAI compatibility layer.",
    ),
    CatalogEntry(
        id="google-gemini",
        display_name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        # /chat/completions answers; only /models is absent from this surface.
        supports_model_listing=False,
        api_key_url="https://aistudio.google.com/apikey",
        note="The OpenAI-compatible surface does not list models — enter a model name directly.",
    ),
    CatalogEntry(
        id="groq",
        display_name="Groq",
        base_url="https://api.groq.com/openai/v1",
        supports_model_listing=True,
        api_key_url="https://console.groq.com/keys",
    ),
    CatalogEntry(
        id="mistral",
        display_name="Mistral",
        base_url="https://api.mistral.ai/v1",
        supports_model_listing=True,
        api_key_url="https://console.mistral.ai/api-keys",
    ),
    CatalogEntry(
        id="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        supports_model_listing=True,
        api_key_url="https://platform.deepseek.com/api_keys",
    ),
    CatalogEntry(
        id="xai",
        display_name="xAI",
        base_url="https://api.x.ai/v1",
        supports_model_listing=True,
        api_key_url="https://console.x.ai",
    ),
    CatalogEntry(
        id="cerebras",
        display_name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        supports_model_listing=True,
        api_key_url="https://cloud.cerebras.ai",
    ),
    CatalogEntry(
        id="together",
        display_name="Together AI",
        base_url="https://api.together.xyz/v1",
        supports_model_listing=True,
        api_key_url="https://api.together.xyz/settings/api-keys",
    ),
    CatalogEntry(
        id="fireworks",
        display_name="Fireworks AI",
        base_url="https://api.fireworks.ai/inference/v1",
        supports_model_listing=True,
        api_key_url="https://fireworks.ai/account/api-keys",
    ),
    CatalogEntry(
        id="deepinfra",
        display_name="DeepInfra",
        base_url="https://api.deepinfra.com/v1/openai",
        supports_model_listing=True,
        api_key_url="https://deepinfra.com/dash/api_keys",
    ),
    CatalogEntry(
        id="perplexity",
        display_name="Perplexity",
        base_url="https://api.perplexity.ai/v1",
        supports_model_listing=True,
        api_key_url="https://www.perplexity.ai/settings/api",
    ),
    CatalogEntry(
        id="huggingface",
        display_name="Hugging Face",
        base_url="https://router.huggingface.co/v1",
        supports_model_listing=True,
        api_key_url="https://huggingface.co/settings/tokens",
    ),
    CatalogEntry(
        id="nebius",
        display_name="Nebius AI Studio",
        base_url="https://api.studio.nebius.com/v1",
        supports_model_listing=True,
        api_key_url="https://studio.nebius.com/settings/api-keys",
    ),
    CatalogEntry(
        id="novita",
        display_name="Novita AI",
        base_url="https://api.novita.ai/v3/openai",
        supports_model_listing=True,
        api_key_url="https://novita.ai/settings/key-management",
    ),
    CatalogEntry(
        id="hyperbolic",
        display_name="Hyperbolic",
        base_url="https://api.hyperbolic.xyz/v1",
        supports_model_listing=True,
        api_key_url="https://app.hyperbolic.xyz/settings",
    ),
    CatalogEntry(
        id="siliconflow",
        display_name="SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        supports_model_listing=True,
        api_key_url="https://cloud.siliconflow.cn/account/ak",
    ),
    CatalogEntry(
        id="litellm",
        display_name="LiteLLM proxy",
        base_url=None,
        supports_model_listing=True,
        requires_base_url=True,
        note="A self-hosted proxy you run. Adds virtual keys, cost governance and an MCP gateway; needs standing up first.",
    ),
    CatalogEntry(
        id=OTHER_ENTRY_ID,
        display_name="Other (OpenAI-compatible)",
        base_url=None,
        supports_model_listing=True,
        requires_base_url=True,
        note="Anything exposing an OpenAI-compatible API. Supply its base URL and key.",
    ),
)

_BY_ID = {entry.id: entry for entry in PROVIDER_CATALOG}


def catalog_entry(entry_id: str) -> CatalogEntry | None:
    return _BY_ID.get(entry_id)


def catalog_to_dict(entry: CatalogEntry) -> dict:
    return {
        "id": entry.id,
        "display_name": entry.display_name,
        "base_url": entry.base_url,
        "supports_model_listing": entry.supports_model_listing,
        "requires_base_url": entry.requires_base_url,
        "api_key_url": entry.api_key_url,
        "note": entry.note,
    }
