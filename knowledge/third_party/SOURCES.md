# Third-party source snapshots

This directory contains source copied into Knowledge for local adaptation. These
files are not external service integrations. They are vendored snapshots that
will be adapted behind Knowledge ports over time.

## RAGFlow

- Source: `https://github.com/infiniflow/ragflow.git`
- Snapshot: `2d63ad654dd8a44e5aaf17ca6fc819bd7720027a`
- License: Apache-2.0, copied in `knowledge/third_party/ragflow/LICENSE`
- Copied paths:
  - `common/token_utils.py`
  - `common/file_utils.py`
  - `deepdoc/parser`
  - `rag/flow` without upstream test fixtures
  - `rag/nlp`

Initial intent: reuse and adapt document parsing, chunking, tokenizer, and text
normalization code for Knowledge ingestion.

## Onyx

- Source: `https://github.com/onyx-dot-app/onyx.git`
- Snapshot: `5200dade0709f926f15309dbe48b1e43e680c202`
- License: MIT for copied non-`ee` content, copied in `knowledge/third_party/onyx/LICENSE`
- Copied paths:
  - `backend/onyx/connectors` without old Salesforce shelf test helpers

Initial intent: reuse and adapt connector interfaces, connector implementations,
ACL utilities, and source discovery behavior for Knowledge sources.

## Rules

- Do not copy Onyx `ee` directories into this repository.
- Keep third-party code under `knowledge/third_party` until it is adapted into
  Knowledge-owned modules.
- Prefer thin Knowledge adapters over direct imports from domain services.
- Preserve source commit, license, and copied path metadata when refreshing
  snapshots.
