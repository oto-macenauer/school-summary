"""Custom AI prompt endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import get_manager, get_student_or_404
from ..services.prompt_variables import get_available_variables, resolve_prompt

router = APIRouter(tags=["prompt"])


class PromptRequest(BaseModel):
    prompt: str
    system_instruction: str | None = None


@router.post("/api/students/{name}/prompt")
async def execute_prompt(name: str, body: PromptRequest):
    """Execute a custom prompt with variable resolution."""
    manager = get_manager()
    ctx = get_student_or_404(name)
    gemini = manager.gemini

    if gemini is None:
        raise HTTPException(status_code=400, detail="Gemini API is not configured")

    prompt_text = body.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    # Resolve variables
    resolved_prompt, resolved_vars = resolve_prompt(prompt_text, ctx)

    # Send to Gemini
    result = await gemini.generate_content(
        prompt=resolved_prompt,
        system_instruction=body.system_instruction,
    )

    return {
        "result": result,
        "resolved_variables": resolved_vars,
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/api/students/{name}/prompt/variables")
async def list_variables(name: str):
    """List available prompt variables for a student."""
    ctx = get_student_or_404(name)
    variables = get_available_variables(ctx)
    return {"variables": variables}
