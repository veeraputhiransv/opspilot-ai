# OpsPilot AI — RAG and incident knowledge

## Purpose

Retrieval supplies **evidence from prior incidents and workspace documents** during investigation. It does not plan actions and it does not approve them.

## Pipeline

```text
Document or resolved incident
→ parse (markdown, text, PDF text layer, FAQ-like runbooks)
→ chunk
→ embed via Embedder protocol
→ persist in knowledge_documents + incident_embeddings
→ cosine search in pgvector
→ optional in-process rerank by service + recency
→ inject titles, symptoms, root cause into the historical-incident node
→ cite sources on the timeline and RCA
```

If nothing is similar, the node records “no prior match” and the reasoner must not invent a historical incident number.

## Embedder protocol

```python
class Embedder(Protocol):
    name: str
    dimension: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Default: local hashing embedder `opspilot-hash-v1` (dimension 384) so tests and airplane development work. Production may switch to a hosted embedding model of the **same dimension**, or a migration changes the column.

The model name is stored on each vector row. Mixing models in one table without a migration is invalid.

## Scope

All search is `workspace_id = current workspace`. Cross-workspace retrieval is not allowed.

## Citations

Every retrieved document contributes a source: title, external_id, score. The RCA “similar incidents” section lists those ids. Hallucinated `INC-` numbers that are not in the result set are an eval failure.

## Chunking

Incident write-ups are stored as a small number of sections (symptoms, root cause, resolution) rather than arbitrary 512-token windows, because operators query by incident. Uploaded runbooks use overlapping character chunks (~800 chars, 100 overlap) with `chunk_index`.
