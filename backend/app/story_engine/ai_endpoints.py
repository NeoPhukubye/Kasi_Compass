"""
Companion Mode "Gemini tour guide" — POST /story-engine/companion/chat.

Kept in its own module and mounted lazily by api.py so the core runtime
API never imports a vendor SDK at module level (see
test_runtime_api_does_not_import_the_ai_tool in test_translation_tool.py).

Behavior:

  1. With no GEMINI_API_KEY configured, the endpoint answers 503 with a
     clear message. The guide is an opt-in, key-gated surface.
  2. With a key, the question is sent to Gemini through the modern
     `google-genai` client for a live tour-guide answer.
  3. Any SDK or upstream failure surfaces as a 500 carrying the underlying
     error, so Render logs show exactly what went wrong.

The API key lives only in backend environment variables, never in browser JS.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from google import genai

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

ai_router = APIRouter(prefix="/story-engine", tags=["Story Engine — AI"])

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"


class CompanionChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    stop_context: str = "Shosholoza Meyl Corridor (South Africa)"


class CompanionChatResponse(BaseModel):
    status: str
    reply: str


@ai_router.post("/companion/chat", response_model=CompanionChatResponse)
def companion_chat(request: CompanionChatRequest) -> CompanionChatResponse:
    """Dynamically query Gemini as an expert tour guide for the Kasi Compass route."""
    if not GENAI_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Google GenAI SDK not installed on backend (pip install google-genai)",
        )

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured on backend")

    system_instruction = (
        "You are an expert, culturally rich local tour guide for Kasi Compass, "
        "a project celebrating the Shosholoza rail route from Johannesburg to Cape Town. "
        "You blend historical facts, railway nostalgia for older generations, and vibrant township gig culture "
        "and local stalls for younger generations. Keep answers engaging, informative, and concise."
    )

    full_prompt = (
        f"{system_instruction}\n\n"
        f"Context Location/Stop: {request.stop_context}\n"
        f"User Question: {request.prompt}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=full_prompt,
        )
        return CompanionChatResponse(status="success", reply=response.text)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI guide generation failed: {str(exc)}",
        ) from exc