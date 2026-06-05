"""Standalone WorkplaceThinker API.

This API can run independently for product demos, while the full fork can still
reuse DocThinker's upload, chat, memory, and KG machinery.

Enhanced with Memory System for continuous learning and pattern recognition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .harness import WorkplaceInsightHarness


# === 会话管理 ===
active_sessions: Dict[str, WorkplaceInsightHarness] = {}


def get_or_create_session(session_id: Optional[str] = None) -> tuple[str, WorkplaceInsightHarness]:
    """获取现有会话或创建新会话"""
    if session_id and session_id in active_sessions:
        return session_id, active_sessions[session_id]
    
    new_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
    harness = WorkplaceInsightHarness(
        session_id=new_id,
        enable_memory=True
    )
    active_sessions[new_id] = harness
    return new_id, harness


# === 请求模型 ===
class WorkplaceAnalyzeRequest(BaseModel):
    question: str = ""
    chat_messages: List[Dict[str, Any]] = Field(default_factory=list)
    uploaded_texts: List[Dict[str, str]] = Field(default_factory=list)
    org_chart: List[Dict[str, Any]] = Field(default_factory=list)
    use_llm: bool = False
    session_id: Optional[str] = None
    use_memory: bool = True
    save_to_memory: bool = True


class WorkplaceRawAnalyzeRequest(BaseModel):
    information: str
    question: str = ""
    org_chart: List[Dict[str, Any]] = Field(default_factory=list)
    use_llm: bool = False
    session_id: Optional[str] = None
    use_memory: bool = True
    save_to_memory: bool = True


class MemoryExportRequest(BaseModel):
    session_id: str


class MemoryImportRequest(BaseModel):
    session_id: str
    memory_data: Dict[str, Any]


# === 应用初始化 ===
app = FastAPI(
    title="WorkplaceThinker",
    description="Workplace relationship graph and hidden-risk insight API built on DocThinker, with memory system.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === API 路由 ===
@app.get("/", response_class=HTMLResponse)
async def workplace_radar_home() -> str:
    html_path = Path(__file__).resolve().parents[1] / "apps" / "workplace_radar.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>WorkplaceThinker</h1><p>apps/workplace_radar.html not found.</p>"


@app.post("/api/v1/workplace/analyze")
async def analyze_workplace(request: WorkplaceAnalyzeRequest) -> Dict[str, Any]:
    session_id, harness = get_or_create_session(request.session_id)
    result = await harness.analyze_structured(
        chat_messages=request.chat_messages,
        uploaded_texts=request.uploaded_texts,
        org_chart=request.org_chart,
        question=request.question,
        use_llm=request.use_llm,
    )
    result["session_id"] = session_id
    return result


@app.post("/api/v1/workplace/analyze/raw")
async def analyze_workplace_raw(request: WorkplaceRawAnalyzeRequest) -> Dict[str, Any]:
    session_id, harness = get_or_create_session(request.session_id)
    result = await harness.analyze_information(
        request.information,
        question=request.question,
        org_chart=request.org_chart,
        use_llm=request.use_llm,
    )
    result["session_id"] = session_id
    return result


# === 记忆管理 API ===
@app.get("/api/v1/memory/sessions")
async def list_sessions() -> Dict[str, Any]:
    """列出所有活跃会话"""
    sessions_info = []
    for sid, harness in active_sessions.items():
        stats = harness.get_memory_stats() or {}
        sessions_info.append({
            "session_id": sid,
            "stats": stats
        })
    return {
        "sessions": sessions_info,
        "count": len(sessions_info)
    }


@app.get("/api/v1/memory/stats/{session_id}")
async def get_memory_stats(session_id: str) -> Dict[str, Any]:
    """获取指定会话的记忆统计"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    stats = active_sessions[session_id].get_memory_stats()
    return {
        "session_id": session_id,
        "stats": stats
    }


@app.get("/api/v1/memory/profile/{session_id}/{person_name}")
async def get_person_profile(session_id: str, person_name: str) -> Dict[str, Any]:
    """获取指定人物的画像"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    profile = active_sessions[session_id].get_person_profile(person_name)
    return {
        "session_id": session_id,
        "person": person_name,
        "profile": profile
    }


@app.post("/api/v1/memory/export")
async def export_memory(request: MemoryExportRequest) -> Dict[str, Any]:
    """导出会话记忆"""
    if request.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    memory_data = active_sessions[request.session_id].export_memory()
    return {
        "session_id": request.session_id,
        "memory_data": memory_data
    }


@app.post("/api/v1/memory/import")
async def import_memory(request: MemoryImportRequest) -> Dict[str, Any]:
    """导入记忆到会话"""
    session_id, harness = get_or_create_session(request.session_id)
    success = harness.import_memory(request.memory_data)
    return {
        "session_id": session_id,
        "success": success
    }


@app.post("/api/v1/memory/clear/{session_id}")
async def clear_session_memory(session_id: str) -> Dict[str, Any]:
    """清空会话记忆"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    success = active_sessions[session_id].clear_session_memory()
    return {
        "session_id": session_id,
        "success": success
    }


@app.delete("/api/v1/memory/session/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """删除会话"""
    if session_id in active_sessions:
        del active_sessions[session_id]
        return {"session_id": session_id, "deleted": True}
    raise HTTPException(status_code=404, detail="Session not found")

