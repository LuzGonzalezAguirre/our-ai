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
