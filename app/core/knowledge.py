import math
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk, KnowledgeSource
from app.providers.embeddings import embedding_provider


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 160,
) -> list[str]:
    clean = "\n".join(
        line.rstrip()
        for line in text.strip().splitlines()
    ).strip()

    if not clean:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(clean):
        end = min(start + chunk_size, len(clean))
        chunk = clean[start:end]

        if end < len(clean):
            split_at = max(
                chunk.rfind("\n"),
                chunk.rfind(". "),
                chunk.rfind(" "),
            )
            if split_at > chunk_size // 2:
                end = start + split_at + 1
                chunk = clean[start:end]

        chunk = chunk.strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(clean):
            break

        start = max(end - overlap, start + 1)

    return chunks


def _cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    if len(left) != len(right) or not left:
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))

    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot / (left_norm * right_norm)


class KnowledgeStore:
    async def add_text(
        self,
        project_id: str,
        title: str,
        content: str,
    ) -> tuple[KnowledgeSource, int]:
        chunks = _chunk_text(content)

        if not chunks:
            raise ValueError("El contenido no produjo fragmentos válidos.")

        embeddings = await embedding_provider.embed(chunks)

        if len(embeddings) != len(chunks):
            raise RuntimeError(
                "La cantidad de embeddings no coincide con los fragmentos."
            )

        now = _utcnow()
        source_id = str(uuid4())

        source = KnowledgeSource(
            id=source_id,
            project_id=project_id,
            title=title.strip(),
            content=content.strip(),
            created_at=now,
        )

        async with SessionLocal() as session:
            async with session.begin():
                session.add(source)
                await session.flush()

                chunk_records = [
                    KnowledgeChunk(
                        id=str(uuid4()),
                        source_id=source_id,
                        project_id=project_id,
                        chunk_index=index,
                        content=chunk,
                        embedding=[
                            float(value)
                            for value in embedding
                        ],
                        created_at=now,
                    )
                    for index, (chunk, embedding)
                    in enumerate(zip(chunks, embeddings))
                ]

                session.add_all(chunk_records)

        return source, len(chunks)

    async def list_sources(
        self,
        project_id: str,
    ) -> list[tuple[KnowledgeSource, int]]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(
                    KnowledgeSource,
                    func.count(KnowledgeChunk.id),
                )
                .outerjoin(
                    KnowledgeChunk,
                    KnowledgeChunk.source_id == KnowledgeSource.id,
                )
                .where(KnowledgeSource.project_id == project_id)
                .group_by(KnowledgeSource.id)
                .order_by(KnowledgeSource.created_at.desc())
            )
            return [
                (source, int(chunk_count))
                for source, chunk_count in result.all()
            ]

    async def get_source_detail(
        self,
        project_id: str,
        source_id: str,
    ) -> tuple[KnowledgeSource, list[KnowledgeChunk]] | None:
        async with SessionLocal() as session:
            source = await session.get(
                KnowledgeSource,
                source_id,
            )

            if (
                source is None
                or source.project_id != project_id
            ):
                return None

            result = await session.execute(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.project_id == project_id,
                    KnowledgeChunk.source_id == source_id,
                )
                .order_by(KnowledgeChunk.chunk_index)
            )
            chunks = list(result.scalars().all())
            return source, chunks

    async def delete_source(
        self,
        project_id: str,
        source_id: str,
    ) -> bool:
        async with SessionLocal() as session:
            async with session.begin():
                source = await session.get(
                    KnowledgeSource,
                    source_id,
                )

                if (
                    source is None
                    or source.project_id != project_id
                ):
                    return False

                await session.execute(
                    delete(KnowledgeSource).where(
                        KnowledgeSource.id == source_id
                    )
                )
                return True

    async def retrieve(
        self,
        project_id: str,
        query: str,
        top_k: int = 3,
    ) -> list[tuple[KnowledgeChunk, float]]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.project_id == project_id
                )
            )
            chunks = list(result.scalars().all())

        if not chunks:
            return []

        query_embedding = (
            await embedding_provider.embed(query)
        )[0]

        scored = [
            (
                chunk,
                _cosine_similarity(
                    query_embedding,
                    [
                        float(value)
                        for value in chunk.embedding
                    ],
                ),
            )
            for chunk in chunks
        ]

        scored.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return scored[:top_k]


knowledge_store = KnowledgeStore()
