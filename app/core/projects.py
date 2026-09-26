from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Project


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStore:
    async def list_projects(self) -> list[Project]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Project).order_by(
                    Project.created_at,
                    Project.name,
                )
            )
            return list(result.scalars().all())

    async def get(self, project_id: str) -> Project | None:
        async with SessionLocal() as session:
            return await session.get(Project, project_id)

    async def create(
        self,
        name: str,
        description: str,
    ) -> Project:
        now = _utcnow()

        project = Project(
            id=str(uuid4()),
            name=name.strip(),
            description=description.strip(),
            created_at=now,
            updated_at=now,
        )

        async with SessionLocal() as session:
            async with session.begin():
                session.add(project)

        return project

    async def get_default(self) -> Project | None:
        return await self.get(settings.default_project_id)


project_store = ProjectStore()
