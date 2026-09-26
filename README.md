# Our AI

Self-hosted AI Core using FastAPI, Ollama and Qwen.

## Current features

- Local model inference through Ollama
- `POST /v1/chat`
- Persistent conversations and messages
- PostgreSQL storage
- Conversation history API
- Browser chat interface
- Model provider abstraction

## Local setup

### 1. Install dependencies

```powershell
cd C:\Users\Aguirre\source\repos\our-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

Create a database named:

```text
our_ai
```

For a default local PostgreSQL installation:

```sql
CREATE DATABASE our_ai;
```

### 3. Configure environment

Copy:

```powershell
Copy-Item .env.example .env
```

Then update the PostgreSQL user/password in `.env` if needed.

Default:

```text
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/our_ai
```

### 4. Start Ollama

Make sure the local model is available:

```powershell
ollama list
```

The default model is:

```text
qwen3:1.7b
```

### 5. Start Our AI

```powershell
uvicorn app.main:app --reload
```

Open:

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

## Database tables

Tables are created automatically when FastAPI starts:

- `ai_conversations`
- `ai_messages`

Conversation history remains available after the API is restarted.
