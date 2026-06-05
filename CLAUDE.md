# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智扫通 (Smart Sweep) — an intelligent customer service system for robot vacuum cleaners (扫地/扫拖机器人). It uses a LangChain/LangGraph ReAct agent with tool-calling, RAG (retrieval-augmented generation) over a Milvus vector store with hybrid search (Dense + BM25 + RRF + Reranker), Multi-Query / HyDE query enhancement, long-conversation memory with auto-summarization, and dynamic prompt switching for report generation. The project supports **three LLM providers** (DeepSeek, QWen/Tongyi, OpenAI) through a unified factory pattern, with DeepSeek as the default chat model and QWen (DashScope) as the default embedding provider.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API keys as environment variables
export DEEPSEEK_API_KEY="your-key"      # For DeepSeek chat (default)
export DASHSCOPE_API_KEY="your-key"     # For QWen embeddings / reranker

# 3. Initialize the database (MySQL 8.4.4 required)
python -c "from db.connection import init_db; init_db()"

# 4. Load knowledge base documents into Milvus
python scripts/manage_kb.py load

# 5. Start a service
streamlit run app.py          # Streamlit web UI (simple demo)
python api_server.py          # FastAPI REST API with auth (recommended)
cd frontend && npm run dev    # React frontend (Vite dev server)
```

## Database

- **MySQL 8.4.4** — 本地数据库，用于持久化存储用户、对话、消息数据
- 数据库名：`smart_sweep`
- 用户名：`sweep_user`
- 密码：`sweep_user_password`
- Host：`localhost`，端口：`3306`
- 字符集：`utf8mb4`（utf8mb4_unicode_ci）
- 连接池大小：5，连接回收时间：3600 秒

连接命令示例：
```bash
mysql -u sweep_user -p'sweep_user_password' smart_sweep
```

数据库表（由 SQLAlchemy ORM 自动创建）：
- `users` — 用户表（id, username, password_hash, display_name, created_at, updated_at）
- `conversations` — 会话表（id, user_id, title, summary_text, summarized_count, created_at, updated_at）
- `messages` — 消息表（id, conversation_id, role, content, created_at）

## Commands

### Running the app

```bash
# Streamlit web UI (simple demo, no auth)
streamlit run app.py

# FastAPI OpenAI-compatible server (recommended for production)
python api_server.py
# Then open http://localhost:8000/docs for Swagger UI

# React frontend (development)
cd frontend && npm run dev

# Test the agent directly from CLI
python -m agent.react_agent

# Test RAG service directly
python -m rag.rag_service

# Test hybrid retriever
python -m rag.hybrid_retriever

# Test vector store / document loading
python -m rag.vector_store

# Test query processor (Multi-Query / HyDE)
python -m rag.query_processor

# Test reranker
python -m model.reranker
```

### Knowledge base management

```bash
# Load all documents from data/ into Milvus
python scripts/manage_kb.py load

# Rebuild BM25 indexes
python scripts/rebuild_kb.py
```

### Running evaluations

```bash
# Full RAGAS evaluation pipeline (easy/middle/hard datasets)
python -m eval.rag_eval
```

### API testing

```bash
# Test chat API with multi-turn context
python scripts/test_chat_context.py

# Test chat API basics
python scripts/test_chat_api.py
```

### No unit tests yet

There is no unit test suite at this time (see [TODO.md](TODO.md)).

## Architecture

The project follows a layered architecture with 7 layers:

### Layer 1: Entry Points

- [app.py](app.py) — Streamlit chat UI. Minimal demo: instantiates `ReactAgent` once per session, stores messages in `st.session_state`. No database persistence, no auth.
- [api_server.py](api_server.py) — FastAPI server with two API groups:
  - **OpenAI-compatible** `POST /v1/chat/completions` — for Open WebUI and other third-party frontends. Parses the full `messages` list into `ConversationMemory` for multi-turn context awareness. Supports streaming (SSE) and non-streaming modes.
  - **RESTful API** — full auth + CRUD:
    - `POST /api/auth/register` / `POST /api/auth/login` — user registration & login (returns JWT)
    - `GET/POST /api/conversations` — list/create conversations
    - `GET/DELETE /api/conversations/{id}` — get/delete conversation
    - `GET /api/conversations/{id}/messages` — get all messages
    - `POST /api/conversations/{id}/messages` — send message (supports `?stream=true` for SSE streaming)

### Layer 2: ReAct Agent

- [agent/react_agent.py](agent/react_agent.py) — `ReactAgent` class built via LangChain `create_agent()`. Key behaviors:
  - **Constructor accepts `ConversationMemory`** — pass an existing memory to restore history; omit for new sessions.
  - `execute_stream(query)` — main entry point. Yields chunk dicts: `{"type": "text", "subtype": "thinking"|"tool_result"|"answer", "content": ..., ...extra}` and `{"type": "rag_docs", "docs": [...], "query": "..."}`.
  - **Memory-augmented queries** — prepends `memory.get_context()` (summary + recent messages) to the query before sending to the agent, enabling multi-turn context awareness without passing full history to the LLM every time.
  - **RAG cache isolation** — uses `contextvars.ContextVar` (`_rag_results_ctx`) so concurrent users' RAG results never cross-contaminate.
  - **Anti-duplicate message insertion** — checks if the last memory message is the same user query before adding.
  - Uses `stream_mode="values"` to yield each message as the agent thinks/tools/replies.

- [agent/tools/agent_tools.py](agent/tools/agent_tools.py) — Eight tools registered with the agent:
  1. `rag_summarize` — RAG retrieval + summarization; caches retrieved docs in ContextVar for frontend display
  2. `get_weather` — mock weather tool (TODO: real API)
  3. `get_user_city` — returns random Chinese city
  4. `get_user_id` — returns random user ID (1001-1006)
  5. `get_current_month` — returns random month (2025-01 ~ 2025-12)
  6. `fetch_external_data` — reads CSV keyed by user_id + month; fields: 特征, 效率, 耗材, 对比
  7. `fill_context_for_report` — no-op tool that triggers middleware to switch to report-generation mode
  8. `drain_rag_results` / `_rag_results_ctx` — utility functions for consuming cached RAG docs per agent step

- [agent/tools/middleware.py](agent/tools/middleware.py) — Three middleware hooks:
  1. `monitor_tool` (`@wrap_tool_call`) — logs every tool invocation; intercepts `fill_context_for_report` to set `context["report"] = True`.
  2. `log_before_model` (`@before_model`) — logs message count and latest message before each model call.
  3. `report_prompt_switch` (`@dynamic_prompt`) — swaps the system prompt to a report-generation prompt when `context["report"]` is `True`.

### Layer 3: Conversation Memory

- [agent/ConversationMemory.py](agent/ConversationMemory.py) — Manages long conversations via auto-summarization:
  - **Incremental summarization** — when unsummarized character count exceeds `threshold` (default 1000), triggers LLM to summarize older messages, keeping the most recent `keep_recent_count` (default 6) messages intact.
  - `get_context()` — returns `summary_text + recent unsummarized messages` formatted for LLM consumption. Can limit recent messages via `recent_context_count` config (default 10).
  - **Configurable LLM** — summary LLM provider and model are configurable in `config/agent.yaml` → `memory` section (default: DeepSeek deepseek-v4-flash).
  - **Pydantic BaseModel** — all state is serializable, can be synced to DB.
  - Persisted to MySQL via `Conversation.summary_text` and `Conversation.summarized_count` columns.

### Layer 4: RAG Pipeline (Hybrid Search + Query Enhancement)

- [rag/vector_store.py](rag/vector_store.py) — `VectorStoreService` manages the Milvus vector database (via milvus-lite embedded deployment):
  - Uses `RecursiveCharacterTextSplitter` with Chinese-friendly separators (configured in [config/chroma.yaml](config/chroma.yaml)).
  - Document loading is idempotent via MD5 deduplication — each file's hash is stored in `md5.txt` and checked before loading.
  - Supports `.txt` and `.pdf` files from the `data/` directory.
  - Native BM25 sparse retrieval via Milvus `Function` API.
  - Hybrid search: Dense (COSINE) + BM25 + RRF fusion via `hybrid_search()` with `RRFRanker`.
  - Document management: `get_sources()`, `delete_by_source()`, `delete_by_ids()`, `update_source()`.

- [rag/hybrid_retriever.py](rag/hybrid_retriever.py) — `HybridRetriever` orchestrates the full retrieval pipeline:
  1. **Query enhancement** (optional) — Multi-Query rewriting and/or HyDE via `QueryProcessor`
  2. **Multi-query retrieval** — for each query variant, execute Milvus Dense+BM25+RRF hybrid search
  3. **Merge & deduplicate** — combine results, remove duplicates by ID and content prefix
  4. **Truncate** — cap at `max_rerank_input` before sending to reranker
  5. **Rerank** (optional) — DashScope or FlagEmbedding reranker for final precision
  6. **Return Top final_k**

- [rag/reranker.py](rag/reranker.py) — `BaseReranker` abstract class with two backends:
  - `DashScopeReranker`: Alibaba Cloud gte-rerank-v2 API (default, no local model needed).
  - `FlagEmbeddingReranker`: Local BAAI/bge-reranker-v2-m3 model.

- [rag/query_processor.py](rag/query_processor.py) — `QueryProcessor` for pre-retrieval query enhancement:
  - **Multi-Query**: Rewrites the original query into N different-angle variants (configurable, default 3), each searched independently. Improves recall for ambiguous/short queries.
  - **HyDE** (Hypothetical Document Embeddings): Generates a hypothetical answer document via LLM, appends it to the query for denser vector representation. Higher cost (extra LLM call), recommended only for hard queries.
  - Both features can be independently toggled in [config/rag.yaml](config/rag.yaml) → `query_processing`.
  - Includes `deduplicate_documents()` utility for post-retrieval deduplication.

- [rag/rag_service.py](rag/rag_service.py) — `RAGSummarizeService` wraps the retriever + prompt template + LLM into a LangChain chain. Multiple output methods:
  - `rag_summarize()` — answer only
  - `rag_summarize_with_context()` — answer + concatenated context (for eval)
  - `rag_summarize_with_docs()` — answer + individual doc list (for RAGAS per-document metrics)
  - Also exposes document management methods (delegated to VectorStoreService).
  - Config toggle: `hybrid_search.enabled` → decides whether to use HybridRetriever or pure Dense.

### Layer 5: Model & Config

- [model/factory.py](model/factory.py) — Unified factory pattern for chat models, embedding models, and rerankers. Dispatch map:
  - Chat: `"deepseek"` → `model.deepseek`, `"qwen"` → `model.qwen`, `"openai"` → `model.openai`
  - Embedding: same dispatch keys
  - Reranker: delegates to `model.reranker.create_reranker()`
  - Config-driven: provider and model names from [config/agent.yaml](config/agent.yaml). Module-level singletons (`chat_model`, `embedding_model`) for backward compatibility.
- [model/deepseek.py](model/deepseek.py) — DeepSeek chat model via `langchain_deepseek.ChatDeepSeek`. No embedding support (raises `NotImplementedError`).
- [model/qwen.py](model/qwen.py) — QWen/Tongyi chat via `ChatTongyi`, embeddings via `DashScopeEmbeddings`. Reads `DASHSCOPE_API_KEY` from environment.
- [model/openai.py](model/openai.py) — OpenAI chat via `ChatOpenAI`, embeddings via `OpenAIEmbeddings`. Reads `OPENAI_API_KEY` from environment.
- [model/reranker.py](model/reranker.py) — Reranker module (moved from rag/): `BaseReranker`, `DashScopeReranker`, `FlagEmbeddingReranker`, and `create_reranker()` factory.
- [config/](config/) — YAML config files:
  - `agent.yaml` — model provider/name, external data path, **memory module** config (threshold, keep_recent_count, summary LLM, etc.)
  - `database.yaml` — MySQL connection + JWT secret/algorithm/expiry + bcrypt rounds
  - `chroma.yaml` — vector store settings: chunking, data paths, MD5 store (note: file kept for backward compat, Milvus settings moved to rag.yaml)
  - `prompts.yaml` — prompt file paths (system, rag, report)
  - `rag.yaml` — Milvus connection + hybrid search (dense_k, sparse_k, rrf_k, final_k) + query processing (multi_query, hyde) + reranker config + knowledge base management
- [prompts/](prompts/) — Four prompt templates: `system_prompt.txt`, `report_prompt.txt`, `rag_summarize_prompt.txt`, `memory_summary_prompt.txt`

### Layer 6: Services & Data Access

- [services/auth_service.py](services/auth_service.py) — `AuthService`: orchestrates registration (check duplicates → hash password → create user → issue JWT) and login (verify credentials → issue JWT).
- [services/conversation_service.py](services/conversation_service.py) — `ConversationService`: CRUD for conversations with ownership verification, message listing.
- [services/chat_service.py](services/chat_service.py) — `ChatService`: the core orchestration layer that ties Agent + Memory + DB together:
  - `load_conversation_memory()` — rebuilds `ConversationMemory` from DB messages
  - `execute_and_persist()` — full flow: load history → save user msg → run Agent → sync memory summary → save assistant msg → return result
  - `execute_and_persist_stream()` — same as above but yields chunks for SSE streaming
  - `persist_state()` — syncs `ConversationMemory.summary_text` and `summarized_count` back to DB; auto-sets conversation title from first user message

- [db/connection.py](db/connection.py) — SQLAlchemy engine + session factory (`SessionLocal`) + `get_db()` FastAPI dependency + `init_db()` for table creation.
- [db/base.py](db/base.py) — `Base = DeclarativeBase` for all ORM models.
- [db/models/](db/models/) — Three ORM models: `User` (users table), `Conversation` (conversations table), `Message` (messages table). Relationships: User → Conversations (cascade delete), Conversation → Messages (cascade delete).
- [db/repository/](db/repository/) — Repository pattern for data access: `UserRepository`, `ConversationRepository`, `MessageRepository`. Each takes a `Session` in constructor.

### Layer 7: Frontend

- [frontend/](frontend/) — React + TypeScript + Vite project. Provides a web UI for the agent API. Connects to the FastAPI backend at `http://localhost:8000`.

### Supporting Layers

- [auth/](auth/) — Authentication modules:
  - `jwt_handler.py` — JWT creation (`create_access_token`) and verification (`decode_access_token`) using `python-jose`
  - `password_handler.py` — bcrypt password hashing and verification
  - `dependencies.py` — `get_current_user()` FastAPI dependency: extracts Bearer token, decodes JWT, queries user

- [schemas/](schemas/) — Pydantic request/response models for the REST API:
  - `auth_schemas.py` — `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserResponse`
  - `conversation_schemas.py` — `ConversationListItem`, `ConversationListResponse`, `CreateConversationRequest`, `ConversationDetailResponse`
  - `message_schemas.py` — `MessageItem`, `MessageListResponse`, `MessageSendRequest`, `MessageSendResponse`

- [utils/](utils/) — Utility modules:
  - [utils/path_tool.py](utils/path_tool.py) — `get_abs_path()` resolves paths relative to project root
  - [utils/config_handler.py](utils/config_handler.py) — loads YAML configs into module-level dicts: `rag_conf`, `chroma_conf`, `prompts_conf`, `agent_conf`, `memory_conf`, `database_conf`
  - [utils/prompt_loader.py](utils/prompt_loader.py) — reads prompt text files
  - [utils/logger_handler.py](utils/logger_handler.py) — custom logger: console (INFO) + timestamped file in `logs/` (DEBUG)

- [eval/](eval/) — RAGAS evaluation pipeline with easy/middle/hard datasets. Uses a custom `token_usage_parser` for cost tracking.

- [scripts/](scripts/) — Utility scripts:
  - `manage_kb.py` — knowledge base document management
  - `rebuild_kb.py` — rebuild BM25 indexes
  - `test_chat_api.py` / `test_chat_context.py` — API testing
  - `start_server.bat` — Windows batch launcher

## Key Design Patterns

### Multi-turn conversation with memory summarization

The system handles long conversations through `ConversationMemory`:
1. Each user/assistant message is added to `memory.messages`
2. When unsummarized text exceeds `threshold` characters, an LLM (configurable, default DeepSeek flash) generates an incremental summary of older messages
3. The most recent `keep_recent_count` messages are always kept in full
4. `get_context()` returns `[summary] + [recent N messages]` — this goes into the agent's query for context awareness
5. Summary state (`summary_text`, `summarized_count`) is persisted to MySQL `conversations` table
6. Full message history is stored in `messages` table for session restoration

### Dynamic prompt switching

The agent switches between normal and report-generation behavior via middleware, not by changing the agent itself. When `fill_context_for_report` is called, `monitor_tool` sets `context["report"] = True`, and `report_prompt_switch` replaces the system prompt before the next model call. Any non-report tool calls made before `fill_context_for_report` will use the normal prompt and may produce incorrect behavior for report scenarios.

### ReAct flow

The agent follows Think → Act → Observe → Think. Tools are LangChain `@tool`-decorated functions. The system prompt instructs the model to output natural-language reasoning before each tool call, and to stop after 5 failed tool attempts.

### Document deduplication

`VectorStoreService.load_documents()` checks `md5.txt` (configured as `md5_hex_store`) before adding any file. The same file won't be re-embedded on subsequent runs.

### Hybrid search pipeline with query enhancement

When `hybrid_search.enabled: true` in [config/rag.yaml](config/rag.yaml), the RAG pipeline uses:

```
Query → [QueryProcessor: Multi-Query / HyDE] → N query variants
  → [Milvus: Dense(COSINE) + BM25 + RRF fusion] × N
  → Merge & Deduplicate → Truncate → [Reranker (DashScope gte-rerank-v2)] → Top-K
```

- Set `hybrid_search.enabled: false` to fall back to pure Dense vector retrieval
- Set `query_processing.multi_query.enabled: false` to disable multi-query
- Set `query_processing.hyde.enabled: false` to disable HyDE
- Set `reranker.enabled: false` to skip reranking while keeping hybrid search

### Multi-provider model architecture

The factory in [model/factory.py](model/factory.py) dispatches to provider-specific modules. Switching providers requires only a config change in [config/agent.yaml](config/agent.yaml):
```yaml
chat_model_provider: deepseek   # deepseek | qwen | openai
chat_model_name: deepseek-v4-flash
embedding_model_provider: qwen  # qwen | openai (deepseek has no embedding)
embedding_model_name: text-embedding-v4
```

### RAG result streaming with ContextVar isolation

`rag_summarize` tool stores retrieved documents in a `ContextVar`-based cache. After each agent step, `drain_rag_results()` consumes the cache and yields `rag_docs` chunks to the frontend. ContextVar ensures multi-user isolation — each request's cache is scoped to its own execution context.

### Repository + Service pattern

Data access follows a layered approach:
- **Repository** (`db/repository/`) — raw SQLAlchemy queries, one class per entity
- **Service** (`services/`) — business logic orchestration, calls repositories
- **API routes** (`api_server.py`) — HTTP handling, calls services
- All DB sessions are managed via FastAPI's `Depends(get_db)` dependency injection

## Important rules

- Conversation and code comment should be in Chinese.
- Use `get_abs_path()` from [utils/path_tool.py](utils/path_tool.py) for all file I/O — do not use raw relative paths.
- The default chat model provider is **DeepSeek** (not QWen). Embeddings still use QWen (DashScope).
- When working with the API server, remember it uses JWT auth — endpoints under `/api/` require `Authorization: Bearer <token>` header.
- The OpenAI-compatible `/v1/chat/completions` endpoint does NOT require auth (designed for Open WebUI integration).
