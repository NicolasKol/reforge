"""
LLM Router
Handles AI-powered decompilation and code generation requests.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


# =============================================================================
# Request/Response Models
# =============================================================================

class LLMDecompileRequest(BaseModel):
    """Request for LLM-based decompilation"""
    function_id: str = Field(..., description="Function UUID from database")
    model_provider: str = Field("openai", description="LLM provider: openai, anthropic, ollama")
    model_name: str = Field("gpt-4", description="Model name")
    prompt_template_id: Optional[str] = Field(None, description="Custom prompt template UUID")
    temperature: float = Field(0.7, description="Sampling temperature")
    max_iterations: int = Field(3, description="Max compilation feedback iterations")


class LLMDecompileResponse(BaseModel):
    """Response from LLM decompilation"""
    job_id: str
    status: str
    function_id: str
    model_provider: str
    model_name: str


class DecompilationResult(BaseModel):
    """Final decompilation result"""
    function_id: str
    generated_code: str
    compiles: bool
    asan_clean: Optional[bool] = None
    iteration_count: int
    total_tokens: int
    total_cost_usd: float


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post("/decompile", response_model=LLMDecompileResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_llm_decompile(request: LLMDecompileRequest):
    """
    Submit function for LLM-based decompilation.
    
    **TODO:**
    - Validate function_id exists
    - Load prompt template
    - Enqueue LLM job to Redis
    - Worker: Call LLM API → Compile → ASAN → Iterate
    - Store results to llm_interactions and decompilation_results
    """
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="LLM decompilation not implemented yet"
    )


@router.get("/decompile/{job_id}")
async def get_llm_status(job_id: str):
    """Get LLM decompilation job status"""
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="LLM status not implemented yet"
    )


@router.get("/results/{function_id}", response_model=List[DecompilationResult])
async def get_decompilation_results(function_id: str):
    """
    Get all decompilation attempts for a function.
    
    **TODO:**
    - Query decompilation_results for function_id
    - Include validation metrics (compiles, asan_clean)
    """
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Result retrieval not implemented yet"
    )


@router.get("/prompts", response_model=List[Dict[str, Any]])
async def list_prompt_templates():
    """
    List available prompt templates.
    
    **TODO:**
    - Query prompt_templates table
    - Return active templates by category
    """
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Prompt template listing not implemented yet"
    )


# TODO: Add endpoint for creating/updating prompt templates
# TODO: Add endpoint for batch decompilation
# TODO: Add endpoint for comparing different models
