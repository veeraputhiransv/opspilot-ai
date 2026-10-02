"""Rank the corpus in process, and search the same vectors in Postgres."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.corpus import CORPUS
from app.rag.embeddings import MODEL_NAME, cosine, embed, vector_literal


def rank_corpus(query: str, limit: int = 3) -> list[dict]:
    query_vector = embed(query)
    ranked: list[dict] = []
    for document in CORPUS:
        blob = " ".join(
            [
                document["title"],
                document["service"],
                document["symptoms"],
                document["root_cause"],
                document["resolution"],
            ]
        )
        ranked.append({**document, "similarity": cosine(query_vector, embed(blob))})
    ranked.sort(key=lambda item: item["similarity"], reverse=True)
    return ranked[:limit]


def retrieval_query(*, message: str, service: str, logs: list[dict], commits: list[dict]) -> str:
    parts = [message, service]
    parts.extend(str(entry.get("message", "")) for entry in logs[:8])
    parts.extend(str(commit.get("message", "")) for commit in commits[:5])
    return "\n".join(parts)


async def search_similar(
    session: AsyncSession, query: str, limit: int, workspace_id: UUID
) -> list[dict]:
    literal = vector_literal(embed(query))
    sql = """
            SELECT d.external_id, d.title, d.service, d.symptoms, d.root_cause, d.resolution,
                   1 - (e.embedding <=> CAST(:query AS vector)) AS similarity
            FROM knowledge_documents AS d
            JOIN incident_embeddings AS e ON e.document_id = d.id
            WHERE d.workspace_id = :workspace_id
            ORDER BY e.embedding <=> CAST(:query AS vector)
            LIMIT :limit
            """
    result = await session.execute(
        text(sql),
        {"query": literal, "limit": limit, "workspace_id": workspace_id},
    )
    rows = []
    for row in result.mappings():
        item = dict(row)
        item["similarity"] = float(item["similarity"])
        rows.append(item)
    return rows


def embedding_model_name() -> str:
    return MODEL_NAME
