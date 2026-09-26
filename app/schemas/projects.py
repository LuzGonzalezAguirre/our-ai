from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=80,
    )
    description: str = Field(
        default="",
        max_length=500,
    )


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class KnowledgeCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=140,
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=120000,
    )


class KnowledgeResponse(BaseModel):
    id: str
    project_id: str
    title: str
    chunk_count: int
    created_at: datetime
