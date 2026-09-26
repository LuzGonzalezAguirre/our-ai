from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="Mensaje enviado por el usuario",
    )


class ChatResponse(BaseModel):
    response: str
    model: str
