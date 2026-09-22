"""
AI-powered endpoints for Kasi Compass.

This module is separate from api.py so the core runtime API remains
independent of any AI service (Gemini, etc.). The test
`test_runtime_api_does_not_import_the_ai_tool` enforces this separation.

Include this router only when AI functionality is desired.
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

ai_router = APIRouter(prefix="/story-engine", tags=["Story Engine — AI"])


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
        raise HTTPException(status_code=503, detail="Google Generative AI SDK not installed on backend")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured on backend")

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        system_instruction = (
            "You are an expert, culturally rich local tour guide for Kasi Compass, "
            "a project celebrating the Shosholoza rail route from Johannesburg to Cape Town. "
            "You blend historical facts, railway nostalgia for older generations, and vibrant township gig culture "
            "and local stalls for younger generations. Keep answers engaging, informative, and concise."
        )

        full_prompt = f"{system_instruction}\n\nContext Location/Stop: {request.stop_context}\nUser Question: {request.prompt}"
        response = model.generate_content(full_prompt)

        return CompanionChatResponse(status="success", reply=response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI guide generation failed: {str(e)}")