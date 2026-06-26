from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import app as study_app
from study_memory import get_preference


app = FastAPI(
    title="AI Study Assistant API",
    version="0.1.0",
    description="API local optional pentru o viitoare aplicatie mobila.",
)
INFERENCE_LOCK = threading.Lock()


@app.exception_handler(study_app.GenerationTimeoutError)
async def generation_timeout_handler(
    request: Request,
    error: study_app.GenerationTimeoutError,
) -> JSONResponse:
    return JSONResponse(status_code=504, content={"detail": str(error)})


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    document: str | None = None
    model: str | None = None
    response_mode: Literal["Fast", "Balanced", "Accurate"] = "Balanced"
    session_id: str | None = None


class GenerationRequest(BaseModel):
    topic: str = Field(default="toate documentele", min_length=1, max_length=1000)
    count: int = Field(default=5, ge=1, le=20)
    model: str | None = None
    response_mode: Literal["Fast", "Balanced", "Accurate"] = "Balanced"
    session_id: str | None = None


def configure_model(
    model_name: str | None = None,
    response_mode: str = study_app.DEFAULT_RESPONSE_MODE,
) -> str:
    if not study_app.ollama_is_running():
        raise HTTPException(
            status_code=503,
            detail="Ollama nu raspunde pe PC-ul server.",
        )
    selected_model = (
        model_name
        or get_preference(study_app.MEMORY_DB_PATH, "llm_model")
        or study_app.DEFAULT_LLM_MODEL
    )
    study_app.configure_llama_index(selected_model, response_mode)
    return selected_model


def require_documents() -> None:
    if study_app.count_indexed_chunks() == 0:
        raise HTTPException(
            status_code=409,
            detail="Nu exista documente indexate.",
        )


def resolve_document(reference: str | None) -> dict | None:
    if not reference:
        return None

    normalized_reference = study_app.searchable_text(reference)
    for document in study_app.get_indexed_documents():
        file_name = document.get("file_name", "")
        if normalized_reference in {
            study_app.searchable_text(file_name),
            study_app.searchable_text(Path(file_name).stem),
        }:
            return document

    detected = study_app.detect_document_reference(reference)
    if detected:
        return detected
    raise HTTPException(status_code=404, detail=f"Document negasit: {reference}")


def api_session_id(session_id: str | None) -> str:
    return f"api-{session_id or uuid.uuid4()}"


def response_payload(response) -> dict:
    return {
        "answer": study_app.clean_model_text(str(response)),
        "sources": study_app.response_source_records(response),
        "debug": response.debug if isinstance(response, study_app.StudyResponse) else {},
    }


@app.get("/health")
def health() -> dict:
    study_app.ensure_project_dirs()
    ollama_running = study_app.ollama_is_running()
    return {
        "status": "ok" if ollama_running else "degraded",
        "ollama": ollama_running,
        "project_root": str(study_app.PROJECT_ROOT),
        "documents": len(study_app.get_indexed_documents()),
        "chunks": study_app.count_indexed_chunks(),
        "inference_location": "server_pc",
    }


@app.get("/documents")
def documents() -> dict:
    study_app.ensure_project_dirs()
    return {"documents": study_app.get_indexed_documents()}


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    document = resolve_document(request.document)

    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        if study_app.is_document_inventory_question(request.question):
            answer = study_app.indexed_documents_answer()
            study_app.save_answer_to_memory(
                request.question,
                answer,
                session_id=api_session_id(request.session_id),
            )
            return {"answer": answer, "sources": [], "debug": {}, "model": model}

        response = study_app.query_documents(
            request.question,
            document_override=document,
            response_mode=request.response_mode,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            request.question,
            payload["answer"],
            response=response,
            selected_document=document,
            session_id=api_session_id(request.session_id),
        )
        payload["model"] = model
        return payload


@app.post("/quiz")
def quiz(request: GenerationRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        items, response = study_app.generate_quiz(
            request.topic,
            request.count,
            response_mode=request.response_mode,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            f"Genereaza quiz despre: {request.topic}",
            payload["answer"],
            response=response,
            session_id=api_session_id(request.session_id),
        )
        return {
            "items": items,
            "sources": payload["sources"],
            "debug": payload["debug"],
            "model": model,
        }


@app.post("/flashcards")
def flashcards(request: GenerationRequest) -> dict:
    study_app.ensure_project_dirs()
    require_documents()
    with INFERENCE_LOCK:
        model = configure_model(request.model, request.response_mode)
        items, response = study_app.generate_flashcards(
            request.topic,
            request.count,
            response_mode=request.response_mode,
        )
        payload = response_payload(response)
        study_app.save_answer_to_memory(
            f"Genereaza flashcarduri despre: {request.topic}",
            payload["answer"],
            response=response,
            session_id=api_session_id(request.session_id),
        )
        return {
            "items": items,
            "sources": payload["sources"],
            "debug": payload["debug"],
            "model": model,
        }
