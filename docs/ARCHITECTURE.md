# Architecture

Co-pilot Facultate is a desktop-first product with a client/server architecture.

## Request flow

```text
Desktop app / browser
  -> Streamlit chat UI
  -> FastAPI endpoints when needed
  -> request queue and abuse protection
  -> model routing
  -> optional RAG retrieval
  -> Ollama
  -> streamed answer + citations + Explain Why panel
```

## Client/server model

```text
Client Mode
  - opens the public HTTPS URL in an embedded WebView
  - stores only local app settings/cookies
  - does not run Ollama, ChromaDB, Streamlit or FastAPI

Server Mode
  - starts Ollama
  - starts FastAPI
  - starts Streamlit
  - can expose Streamlit through Cloudflare Tunnel or Tailscale Funnel
  - stores documents, vectors, memory and user data locally
```

The desktop PC is the only AI server. Client devices never download or run models.

## RAG pipeline

```text
Upload document
  -> validate upload size/type
  -> store under current user/workspace
  -> extract text/OCR where available
  -> chunk text with metadata
  -> index into ChromaDB namespace/collection
  -> retrieve only from current user/workspace
  -> answer with citations
```

## Model routing

The assistant can run in Auto, Fast, Balanced or Accurate modes.

- Simple chat and short factual answers use the fast model.
- Normal course/RAG answers prefer the fast/balanced model.
- Complex analysis, comparisons, strategy and professor-style explanations route to the accurate/reasoning model.
- If a slow model times out, routing can fall back to a faster model.

## User isolation

Each profile/workspace owns separate state:

```text
storage/users/<user>/<workspace>/
  documents/
  memory/
  flashcards/
  quizzes/
  plans/
  conversations/
  notebook/
```

Retrieval filters by current user and workspace. A user should never see another user's documents in the UI or retrieval layer.

## Public access

```text
Friend/client
  -> HTTPS Cloudflare Tunnel or Tailscale Funnel
  -> desktop PC Streamlit port 8501
  -> local FastAPI/Ollama/ChromaDB
```

Raw router port forwarding is intentionally not part of the recommended deployment.
