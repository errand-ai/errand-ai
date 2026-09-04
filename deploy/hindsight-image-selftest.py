"""Build-time self-test for the errand-hindsight image.

Run as the last layer of `Dockerfile.hindsight`, offline, as the runtime user.
Its job is to fail the build rather than publish an image whose ONNX path is
broken — the base is upstream's and can change under us, so the properties that
make the image worth deriving are asserted rather than assumed:

  * `transformers` is importable inside /app/api/.venv (its absence is the
    entire reason this image exists);
  * the ONNX embeddings provider still exists and still initialises;
  * the baked graph is the 384-dimension model, and actually embeds;
  * the FlashRank model is actually on disk, and initialises from there;
  * the shipped defaults select onnx + flashrank, and never `rrf`;
  * no torch and no sentence-transformers were pulled in transitively.

Every exit is `sys.exit(str)`, which prints to stderr and exits non-zero, so a
failure names the unsatisfied condition in the build log.
"""

import asyncio
import glob
import importlib.util
import os
import sys

EXPECTED_DIMENSION = 384
EXPECTED_MODEL_ID = "intfloat/multilingual-e5-small"
EXPECTED_FLASHRANK_MODEL = "ms-marco-MiniLM-L-12-v2"

# The two packages the image must not have acquired. The ONNX path avoids them,
# and avoiding them is what keeps this image at a measured 3.85 GB rather than
# the full image's 5.47 GB, so a transitive pull is a silent regression of the
# change's whole premise.
FORBIDDEN_MODULES = ("torch", "sentence_transformers")


def require_env(name: str, expected: str) -> str:
    """Assert a shipped default, and return it for use by the live checks."""
    actual = os.environ.get(name)
    if actual != expected:
        sys.exit(f"FATAL: {name} is {actual!r}, expected {expected!r}")
    return actual


async def main() -> None:
    # The image's own defaults. Checked before anything is loaded so that a
    # mis-set ENV is reported as such, not as a downstream model failure.
    require_env("HINDSIGHT_API_EMBEDDINGS_PROVIDER", "onnx")
    require_env("HINDSIGHT_API_RERANKER_PROVIDER", "flashrank")
    require_env("HINDSIGHT_API_EMBEDDINGS_ONNX_MODEL_ID", EXPECTED_MODEL_ID)
    require_env("HINDSIGHT_API_RERANKER_FLASHRANK_MODEL", EXPECTED_FLASHRANK_MODEL)
    model_path = os.environ["HINDSIGHT_API_EMBEDDINGS_ONNX_MODEL_PATH"]
    tokenizer_path = os.environ["HINDSIGHT_API_EMBEDDINGS_ONNX_TOKENIZER_NAME_OR_PATH"]
    flashrank_cache = os.environ["HINDSIGHT_API_RERANKER_FLASHRANK_CACHE_DIR"]

    # Named separately from the provider import below so that the failure the
    # image exists to prevent reports itself in its own words.
    try:
        import transformers  # noqa: F401
    except ImportError as exc:
        sys.exit(f"FATAL: transformers is not importable inside /app/api/.venv: {exc}")

    try:
        from hindsight_api.engine.cross_encoder import FlashRankCrossEncoder
        from hindsight_api.engine.embeddings import OnnxEmbeddings
    except ImportError as exc:
        sys.exit(f"FATAL: the base image no longer provides the ONNX/FlashRank providers: {exc}")

    if not os.path.isfile(model_path):
        sys.exit(f"FATAL: baked ONNX graph missing at {model_path}")

    embeddings = OnnxEmbeddings(
        model_id=EXPECTED_MODEL_ID,
        model_path=model_path,
        tokenizer_name_or_path=tokenizer_path,
    )
    await embeddings.initialize()

    if embeddings.dimension != EXPECTED_DIMENSION:
        sys.exit(f"FATAL: ONNX graph reports {embeddings.dimension} dimensions, expected {EXPECTED_DIMENSION}")

    # A reported dimension is metadata; a forward pass is the thing that proves
    # the tokenizer and the graph agree.
    vectors = embeddings.encode(["errand bakes its models into the image"])
    if len(vectors) != 1 or len(vectors[0]) != EXPECTED_DIMENSION:
        sys.exit(
            f"FATAL: encode() returned {len(vectors)} vector(s) of width "
            f"{len(vectors[0]) if vectors else 'n/a'}, expected 1 x {EXPECTED_DIMENSION}"
        )

    # Checked before initialising, not after. `Ranker()` *downloads* a missing
    # model from FlashRank's CDN, and the build has network — so initialising
    # alone would happily pass on an image whose reranker was never baked,
    # which is precisely the "first run needs no network" guarantee this file
    # exists to defend. Assert the artefacts are on disk first.
    flashrank_model_dir = os.path.join(flashrank_cache, EXPECTED_FLASHRANK_MODEL)
    if not os.path.isdir(flashrank_model_dir):
        sys.exit(f"FATAL: baked FlashRank model missing at {flashrank_model_dir}")
    if not glob.glob(os.path.join(flashrank_model_dir, "*.onnx")):
        sys.exit(f"FATAL: no ONNX graph inside {flashrank_model_dir}; the model did not bake")

    reranker = FlashRankCrossEncoder(
        model_name=EXPECTED_FLASHRANK_MODEL,
        cache_dir=flashrank_cache,
    )
    await reranker.initialize()

    present = [m for m in FORBIDDEN_MODULES if importlib.util.find_spec(m) is not None]
    if present:
        sys.exit(f"FATAL: unexpectedly present in the image: {', '.join(present)}")

    print(
        f"OK: onnx {EXPECTED_MODEL_ID} @ {EXPECTED_DIMENSION}d, "
        f"flashrank {EXPECTED_FLASHRANK_MODEL}, no torch, no sentence-transformers"
    )


asyncio.run(main())
