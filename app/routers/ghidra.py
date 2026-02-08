"""
Ghidra Router
Handles binary decompilation and analysis requests.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


# =============================================================================
# Request/Response Models
# =============================================================================

class DecompileRequest(BaseModel):
    """Request to decompile a binary"""
    binary_id: str = Field(..., description="Binary UUID from database")
    extract_functions: bool = Field(True, description="Extract individual functions")
    extract_pcode: bool = Field(False, description="Extract Ghidra pcode IR")
    extract_call_graph: bool = Field(True, description="Extract call graph")


class FunctionInfo(BaseModel):
    """Decompiled function information"""
    address: str
    name: str
    signature: str
    decompiled_code: str
    pcode: Optional[str] = None


class DecompileJobResponse(BaseModel):
    """Response after submitting decompilation job"""
    job_id: str
    status: str
    binary_id: str


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.post("/decompile", response_model=DecompileJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_decompile(request: DecompileRequest):
    """
    Submit a binary for decompilation with Ghidra.
    
    **TODO:**
    - Validate binary_id exists in database
    - Enqueue decompilation job to Redis
    - Run Ghidra headless in worker
    - Extract functions and store to database
    """
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ghidra decompilation not implemented yet"
    )


@router.get("/decompile/{job_id}")
async def get_decompile_status(job_id: str):
    """Get decompilation job status"""
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ghidra status not implemented yet"
    )


@router.get("/functions/{binary_id}", response_model=List[FunctionInfo])
async def get_functions(binary_id: str):
    """
    Get all functions extracted from a binary.
    
    **TODO:**
    - Query functions table for binary_id
    - Return function list with decompiled code
    """
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Function listing not implemented yet"
    )


# TODO: Add endpoint for getting single function
# TODO: Add endpoint for call graph retrieval
