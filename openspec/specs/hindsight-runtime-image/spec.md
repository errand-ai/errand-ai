# hindsight-runtime-image Specification

## Purpose

The Hindsight runtime errand publishes and ships: upstream's slim API image at a pinned
tag, plus the two packages its local ONNX embedding path needs, with the embedding and
reranker models baked in so a first run needs no network. Covers what the image must
contain, the defaults it ships, and the assertions its build must make before the image
is allowed to publish.

## Requirements

### Requirement: Derived Hindsight runtime image

The project SHALL publish a Hindsight runtime image derived from the upstream slim API image. The image SHALL be built `FROM ghcr.io/vectorize-io/hindsight-api:<version>-slim` at an exact pinned tag — never `latest` — and SHALL install exactly two Python packages by name, `transformers` and `flashrank`, into the base image's virtual environment at `/app/api/.venv`, each pinned to an exact version. Whatever those two resolve to SHALL be accepted, including a dependency the resolver upgrades in place. The image SHALL NOT patch, replace or vendor any upstream source file.

#### Scenario: Image installs only the two required packages, and brings in no deep-learning runtime

- **WHEN** the derived image is built
- **THEN** the only packages named for installation are `transformers` and `flashrank`
- **AND** any further change to the environment is one the dependency resolver made to satisfy those two
- **AND** neither `torch` nor `sentence-transformers` is present

#### Scenario: Added package versions are pinned

- **WHEN** the Dockerfile is inspected
- **THEN** `transformers` and `flashrank` are each installed at an exact version, so that a later rebuild reproduces the same runtime

#### Scenario: Base tag is pinned

- **WHEN** the Dockerfile is inspected
- **THEN** the `FROM` line names an exact upstream version tag, not `latest-slim`

#### Scenario: Installation targets the base image virtual environment

- **WHEN** packages are installed during the build
- **THEN** the install targets `/app/api/.venv` using `uv`, because that virtual environment contains no `pip` executable

### Requirement: Embedding and reranking models are baked into the image

The derived image SHALL contain the `intfloat/multilingual-e5-small` ONNX graph and its tokenizer, and the FlashRank `ms-marco-MiniLM-L-12-v2` model, placed where the runtime resolves them without a network fetch. A container started from the image with no cache volume and no network access SHALL initialise both the embeddings provider and the reranker successfully.

#### Scenario: First run needs no model download

- **WHEN** a container is started from the derived image with an empty cache directory and no outbound network access
- **THEN** the embeddings provider initialises
- **AND** the reranker initialises
- **AND** no Hugging Face download is attempted

#### Scenario: Embedding dimension is asserted at build time

- **WHEN** the image is built
- **THEN** the build verifies the baked ONNX graph reports 384 dimensions and fails the build if it does not

### Requirement: Image ships ONNX embeddings and FlashRank reranking as defaults

The derived image SHALL default to `HINDSIGHT_API_EMBEDDINGS_PROVIDER=onnx` with `HINDSIGHT_API_EMBEDDINGS_ONNX_MODEL_ID=intfloat/multilingual-e5-small`, and to `HINDSIGHT_API_RERANKER_PROVIDER=flashrank`. The `rrf` provider SHALL NOT be used as the primary reranker. Where a reranker fallback chain is configured, `rrf` MAY be its final member so that recall degrades to fusion order rather than failing.

#### Scenario: Defaults require no caller configuration

- **WHEN** a container is started from the derived image with only a database URL and an LLM endpoint configured
- **THEN** embeddings and reranking are both active without any further environment variables

#### Scenario: rrf is never the primary reranker

- **WHEN** the shipped configuration is inspected
- **THEN** `HINDSIGHT_API_RERANKER_PROVIDER` is not set to `rrf`

### Requirement: Build fails rather than shipping a broken ONNX path

The image build SHALL assert that the ONNX embeddings provider can be imported and initialised, and SHALL fail the build if it cannot. This guards against an upstream slim release that moves the virtual environment, removes the ONNX provider, or changes the tokenizer import.

#### Scenario: Missing transformers fails the build

- **WHEN** the base image changes such that `from transformers import AutoTokenizer` cannot be satisfied inside `/app/api/.venv`
- **THEN** the build fails with an explicit error naming the unsatisfied import
- **AND** no image is published

#### Scenario: Relocated virtual environment fails the build

- **WHEN** the base image no longer provides a virtual environment at `/app/api/.venv`
- **THEN** the build fails rather than installing the packages somewhere the runtime will not load them
