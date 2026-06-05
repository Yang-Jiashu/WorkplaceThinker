"""Standalone WorkplaceThinker API.

This API can run independently for product demos, while the full fork can still
reuse DocThinker's upload, chat, memory, and KG machinery.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .harness import WorkplaceInsightHarness


class WorkplaceAnalyzeRequest(BaseModel):
    question: str = ""
    chat_messages: List[Dict[str, Any]] = Field(default_factory=list)
    uploaded_texts: List[Dict[str, str]] = Field(default_factory=list)
    org_chart: List[Dict[str, Any]] = Field(default_factory=list)
    use_llm: bool = False


class WorkplaceRawAnalyzeRequest(BaseModel):
    information: str
    question: str = ""
    org_chart: List[Dict[str, Any]] = Field(default_factory=list)
    use_llm: bool = False


app = FastAPI(
    title="WorkplaceThinker",
    description="Workplace relationship graph and hidden-risk insight API built on DocThinker.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def workplace_radar_home() -> str:
    html_path = Path(__file__).resolve().parents[1] / "apps" / "workplace_radar.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>WorkplaceThinker</h1><p>apps/workplace_radar.html not found.</p>"


@app.post("/api/v1/workplace/analyze")
async def analyze_workplace(request: WorkplaceAnalyzeRequest) -> Dict[str, Any]:
    harness = WorkplaceInsightHarness()
    return await harness.analyze_structured(
        chat_messages=request.chat_messages,
        uploaded_texts=request.uploaded_texts,
        org_chart=request.org_chart,
        question=request.question,
        use_llm=request.use_llm,
    )


@app.post("/api/v1/workplace/analyze/raw")
async def analyze_workplace_raw(request: WorkplaceRawAnalyzeRequest) -> Dict[str, Any]:
    harness = WorkplaceInsightHarness()
    return await harness.analyze_information(
        request.information,
        question=request.question,
        org_chart=request.org_chart,
        use_llm=request.use_llm,
    )
