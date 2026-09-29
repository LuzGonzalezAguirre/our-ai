# Our AI

Self-hosted AI Core using FastAPI, Ollama, Qwen and PostgreSQL.

## Current features

- Local chat inference through Ollama
- Local embeddings through Ollama
- Qwen3 chat model
- Project-isolated conversations
- Project-isolated knowledge
- Semantic retrieval (RAG)
- Persistent conversations and messages
- PostgreSQL storage
- Browser chat interface
- Create projects from the browser
- Add and remove knowledge from the browser
- Model provider abstraction

## Local setup

### 1. Install dependencies

```powershell
cd C:\Users\Aguirre\source\repos\our-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

```sql
CREATE DATABASE our_ai;
```

### 3. Configure environment

```powershell
Copy-Item .env.example .env
```

Update the PostgreSQL credentials in `.env` when needed.

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_THINK=false

DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/our_ai
```

### 4. Download local models

Chat model:

```powershell
ollama pull qwen3:1.7b
```

Embedding model:

```powershell
ollama pull qwen3-embedding:0.6b
```

Verify:

```powershell
ollama list
```

### 5. Start Our AI

```powershell
uvicorn app.main:app --reload
```

Open the browser UI:

```text
http://localhost:8000
```

API documentation:

```text
http://localhost:8000/docs
```

Health check:

```text
http://localhost:8000/health
```

## Projects

A default project named `General` is created automatically.

Each project has isolated:

- conversations
- messages
- knowledge sources
- semantic search context

New projects can be created from the left sidebar.

## Knowledge / RAG

Open `Conocimiento` for the selected project and paste text with a title.

Our AI will:

1. split the content into chunks
2. generate embeddings locally with `qwen3-embedding:0.6b`
3. store chunks and vectors in PostgreSQL
4. embed each user question
5. compare it with the project's chunks
6. inject the most relevant chunks into the chat context

No external AI API is required.

## Database tables

Tables are created automatically when FastAPI starts:

- `ai_conversations`
- `ai_messages`
- `ai_projects`
- `ai_conversation_projects`
- `ai_knowledge_sources`
- `ai_knowledge_chunks`

Existing conversations are automatically associated with the default
`General` project.


## Action Tracker integration (read-only)

OUR-AI can consume the internal Action Tracker JSON bridge and use deterministic analytics
before asking Qwen to explain the result.

Configure the OUR-AI `.env`:

```text
ACTION_TRACKER_ENABLED=true
ACTION_TRACKER_BASE_URL=http://ACTION-TRACKER-SERVER:8000
ACTION_TRACKER_TOKEN=the-same-private-token-configured-in-action-tracker
ACTION_TRACKER_DEFAULT_USER=
ACTION_TRACKER_TIMEOUT_SECONDS=20
```

`ACTION_TRACKER_DEFAULT_USER` is optional. It is useful in a single-user development
environment so phrases such as "mis acciones" can map to one Action Tracker assignee.
A shared deployment should use authenticated user identity instead.

Action Tracker must have `AT_TOKEN` configured with the same secret. Keep both tokens in
environment variables or local `.env` files and never commit them.

Diagnostic endpoints:

- `GET /v1/integrations/action-tracker/health`
- `GET /v1/integrations/action-tracker/overview`
- `GET /v1/integrations/action-tracker/bottlenecks`
- `GET /v1/integrations/action-tracker/trends?days=90`
- `GET /v1/integrations/action-tracker/actions/CAL-125`

The chat automatically adds live Action Tracker context for recognized action queries.
This first integration is strictly read-only.
