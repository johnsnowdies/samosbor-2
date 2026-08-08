# Samosbor AI Game Telegram Bot — v2
![python-version](https://img.shields.io/badge/python-3.13-blue.svg)
[![langgraph](https://img.shields.io/badge/langgraph-0.2%2B-purple)](https://langchain-ai.github.io/langgraph/)
[![temporal](https://img.shields.io/badge/temporal-1.7%2B-orange)](https://temporal.io/)
[![pgvector](https://img.shields.io/badge/pgvector-0.8-green)](https://github.com/pgvector/pgvector)
[![license](https://img.shields.io/badge/License-GPL%202.0-brightgreen.svg)](LICENSE)

This project based on [ChatGPT Telegram Bot](https://github.com/n3d1117/chatgpt-telegram-bot) with respect to GPL 2.0 license and follows same license

## Plot
This project is implementation of roleplaying game using AI models based on original Samosbor lore.
Samosbor is community built lore done via russian imageboards at 2019-2022

All information about lore can be found at this [wiki](https://neolurk.org/wiki/%D0%92%D1%81%D0%B5%D0%BB%D0%B5%D0%BD%D0%BD%D0%B0%D1%8F_%D0%A1%D0%B0%D0%BC%D0%BE%D1%81%D0%B1%D0%BE%D1%80%D0%B0)

![](https://i.ytimg.com/vi/c19Fryl3XHQ/maxresdefault.jpg)

---

## What's New in v2

v2 is a complete rewrite — a tech demo built to showcase modern LLM engineering patterns.

### LangGraph Agent Pipeline

A 13-node directed graph processes every player message:

```
guardrails → validate_action → memory → rag → build_prompt
→ llm_call → parse → update_state → generate_locations
→ fact_check → npc_simulate
```

Each node is a pure function with a single responsibility. Conditional edges handle branching (e.g., `/start` takes a different path, location changes trigger `generate_locations`). Errors are caught at every step and short-circuit to END.

### RAG (Retrieval-Augmented Generation)

- **Lore knowledge base** stored in PostgreSQL with **pgvector** extension
- **Ollama bge-m3** model produces embeddings on-prem — no external API needed
- On each message: embed the user input → cosine similarity search → inject top-5 lore chunks into the LLM prompt
- The bot plays in a *consistent universe* instead of hallucinating lore on the fly

### Temporal Workflow Orchestration

Every game turn runs inside a **Temporal** workflow (`GameSessionWorkflow`):

- **Durable execution** — survives process crashes and restarts
- **Automatic retries** (3 attempts with exponential backoff, 3 min timeout per run)
- Clean separation: the webhook schedules a workflow, Temporal runs the LangGraph, returns the result

This demonstrates production-grade reliability patterns, not just a simple "call LLM → reply" loop.

### Architecture Overview

| Component | Tech | Role |
|-----------|------|------|
| Bot API | FastAPI + python-telegram-bot | Telegram webhook handler |
| Orchestration | Temporal | Durable workflow execution |
| LLM Pipeline | LangGraph | 13-node agent graph |
| Database | PostgreSQL 16 + pgvector | Game state + vector search |
| Embeddings | Ollama (bge-m3) | On-prem RAG embeddings |
| Cache | Redis | Volatile session cache |
| Observability | Langfuse | LLM call tracing & monitoring |
| Migrations | Alembic | Schema versioning |

### Full Infrastructure

```yaml
services:
  bot          # FastAPI Telegram handler
  temporal     # Workflow orchestration engine
  postgres     # Main DB + pgvector for RAG
  redis        # Cache
  langfuse     # LLM observability
  ollama       # Local embeddings
```

All services run via `docker compose up`.

### Database Model

SQLAlchemy async models covering the full game domain:

- `User`, `GameSession`, `Player`, `Person`
- `Location`, `Floor`, `NPC`, `Item`
- `Conversation` (message history)
- `SocialRelation` (NPC affinity tracking)
- `DocumentChunk` (RAG vector store)
- `Task` (quest tracking)

### Other Improvements

- **Python 3.13** with strict typing (`mypy --strict`)
- **Pydantic v2** schemas with `model_dump` serialization
- **Langfuse** integration for full LLM call tracing
- **Modular package layout** (`bot/langgraph/`, `bot/temporal/`, `bot/rag/`, `bot/models/`, `bot/schemas/`)
- **OpenRouter** support for multi-model inference
- **Sentry** error tracking
- The old v1 was ~6 Python files — v2 is ~30+ organized modules

---

## Prerequisites
- Python 3.13+
- Docker & Docker Compose
- A [Telegram bot](https://core.telegram.org/bots#6-botfather) and its token
- An OpenAI / OpenRouter API key

## Getting Started

```bash
cp .env.example .env
# edit .env with your tokens
docker compose up
```

See `.env.example` for all configuration options.