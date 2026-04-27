# -*- coding: utf-8 -*-
"""前后端分离 API 服务入口。

1) 复用 Python 职业规划核心逻辑main.py
2) 对前端提供 HTTP API
3) 提供前端静态页面访问
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, List, Literal, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from main import initialize_system, process_student_career_planning


app = FastAPI(title="Student Career Plan API", version="1.0.0")

# 开发阶段放开 CORS，便于本地前端调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SYSTEM_COMPONENTS: Optional[tuple] = None
# 咨询对话单独懒加载 LLM，避免首条消息触发整套岗位数据与图谱构建（否则「正在思考」会卡住很久）
_CHAT_LLM: Optional[Any] = None
_BASE_DIR = Path(__file__).resolve().parent
_FRONTEND_DIR = _BASE_DIR / "frontend"
_ASSETS_DIR = _BASE_DIR / "assets"
_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

if _FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(_FRONTEND_DIR)), name="frontend")
app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


@app.middleware("http")
async def simple_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if request.url.path.startswith("/api"):
        print(f"{request.method} {request.url.path} -> {elapsed_ms:.1f} ms")
    return response


class ChatMessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=12000)


class ChatConsultRequest(BaseModel):
    messages: List[ChatMessageItem] = Field(default_factory=list)

    @field_validator("messages")
    @classmethod
    def _limit_turns(cls, v: List[ChatMessageItem]) -> List[ChatMessageItem]:
        if len(v) > 50:
            return v[-50:]
        return v


class PlanRequest(BaseModel):
    form_data: dict = Field(default_factory=dict)
    resume_path: Optional[str] = None
    target_jobs: list[str] = Field(default_factory=list)
    top_k: int = 10
    # True 时使用大模型进行增强匹配（需配置 LLM_API_KEY，耗时会明显增加）
    use_ai: bool = False
    # MBTI 四字母类型（如 INFJ）；与能力自评融合，冲突时以 MBTI 典型特征优先
    mbti_type: str = ""


class CareerGraphVisualRequest(BaseModel):
    """垂直/换岗聚焦图谱：锚点一般为 Top 匹配岗位的 job_id 列表。"""

    student_profile: dict = Field(default_factory=dict)
    anchor_job_ids: list[str] = Field(default_factory=list)
    # 为 True 时仅导出计算机 / IT 相关岗位，节点更少、图谱更稳定
    computer_only: bool = True


def _student_proxy_for_radar(d: dict) -> Any:
    """将 API/前端缓存的学生字典转为雷达图计算可用的简单对象。"""
    from types import SimpleNamespace

    skills: dict[str, int] = {}
    prof = d.get("professional_skills")
    if isinstance(prof, list):
        for k in prof:
            if k:
                skills[str(k)] = 3
    return SimpleNamespace(
        skills=skills,
        experience=d.get("experience") or [],
        certificates=d.get("certificates") or [],
        communication=int(d.get("communication") or 0),
        stress_resistance=int(d.get("stress_resistance") or 0),
        learning_ability=int(d.get("learning_ability") or 0),
        innovation_ability=int(d.get("innovation_ability") or 0),
    )


def _node_tooltip_payload(jp: Any, sp_proxy: Any) -> dict:
    from models.matching_engine import _radar_job_required_series, _radar_student_series

    labels = ["专业技能", "实习能力", "沟通能力", "抗压能力", "学习能力", "创新能力", "证书"]
    stu = _radar_student_series(sp_proxy)
    job_req = _radar_job_required_series(sp_proxy, jp)
    req_sk = list(jp.required_skills or [])
    st_set = {k.lower() for k in getattr(sp_proxy, "skills", {}).keys()}
    met: list[str] = []
    gap: list[str] = []
    for s in req_sk[:20]:
        sl = (s or "").lower().strip()
        if not sl:
            continue
        hit = any(sl == k or sl in k or k in sl for k in st_set)
        (met if hit else gap).append(s)
    bd = jp.to_dimension_dict().get("basic_requirements", {})
    return {
        "job_id": jp.job_id,
        "job_name": jp.job_name,
        "company_name": getattr(jp, "company_name", "") or "",
        "description": (jp.description or "")[:1200],
        "required_skills": req_sk[:32],
        "certificates": list(jp.certificates)[:16] if jp.certificates else [],
        "education_hint": str(bd.get("education", "") or ""),
        "internship_hint": str(bd.get("internship_experience", "") or ""),
        "technical_depth_hint": str(bd.get("technical_depth", "") or ""),
        "radar": {"labels": labels, "student": stu, "job_required": job_req},
        "user_satisfied_skills": met[:16],
        "user_gap_skills": gap[:16],
    }


def _compact_report_data(report_data: dict) -> dict:
    if not isinstance(report_data, dict):
        return {}
    summary = str(report_data.get("executive_summary", ""))
    full_text = str(report_data.get("full_text", ""))
    # 前端仅需可展示内容，截断超长文本，避免浏览器存储和渲染压力过大
    return {
        "title": report_data.get("title", ""),
        "generated_at": report_data.get("generated_at", ""),
        "completeness_score": report_data.get("completeness_score", 0),
        "competitiveness_score": report_data.get("competitiveness_score", 0),
        "executive_summary": summary[:2000],
        "full_text": full_text[:4000],
    }


def _job_display_name(job_profiles: dict, jid: str) -> str:
    jp = job_profiles.get(jid) if job_profiles else None
    return getattr(jp, "job_name", str(jid)) if jp else str(jid)


def _compact_career_path(career_path: dict, job_profiles: Optional[dict] = None) -> dict:
    if not isinstance(career_path, dict):
        return {}
    jp = job_profiles or {}
    vertical_display = []
    seen_v: set[tuple[str, ...]] = set()
    for p in (career_path.get("vertical_paths") or [])[:12]:
        if isinstance(p, list):
            row = [_job_display_name(jp, x) for x in p]
            key = tuple(row)
            if key in seen_v or len(key) < 2:
                continue
            seen_v.add(key)
            vertical_display.append(row)
            if len(vertical_display) >= 5:
                break
    lateral_display = []
    seen_l: set[str] = set()
    for p in (career_path.get("lateral_paths") or [])[:12]:
        if isinstance(p, list) and len(p) >= 2:
            s = f"{_job_display_name(jp, p[0])} → {_job_display_name(jp, p[1])}"
            if s in seen_l:
                continue
            seen_l.add(s)
            lateral_display.append(s)
            if len(lateral_display) >= 5:
                break
    mid_raw = (career_path.get("mid_term_paths") or [])[:5]
    mid_display = [_job_display_name(jp, x) for x in mid_raw]
    return {
        "short_term": _job_display_name(jp, career_path.get("short_term", "")),
        "mid_term_paths": mid_display,
        "long_term_vision": career_path.get("long_term_vision", ""),
        "vertical_display": vertical_display,
        "lateral_display": lateral_display,
        "path_sequence": (career_path.get("path_sequence") or [])[:8],
        "graph_data": {"nodes": [], "edges": []},
    }


def _report_for_export(report_data: dict, job_profiles: Optional[dict] = None) -> dict:
    """用于 Word/PDF 导出的结构化报告数据。"""
    if not isinstance(report_data, dict):
        return {}
    cp = report_data.get("career_path") or {}
    return {
        "title": report_data.get("title", ""),
        "generated_at": report_data.get("generated_at", ""),
        "student_id": report_data.get("student_id", ""),
        "completeness_score": report_data.get("completeness_score", 0),
        "competitiveness_score": report_data.get("competitiveness_score", 0),
        "executive_summary": str(report_data.get("executive_summary", ""))[:6000],
        "match_results": (report_data.get("match_results") or [])[:10],
        "top_job": report_data.get("top_job", ""),
        "career_path": _compact_career_path(cp if isinstance(cp, dict) else {}, job_profiles),
        "action_plan": report_data.get("action_plan") or {},
        "full_text": str(report_data.get("full_text", ""))[:12000],
    }


def _pack_response(result: dict) -> JSONResponse:
    student_profile = _student_profile_to_dict(result.get("student_profile"))
    match_results = result.get("match_results", [])[:10]
    rd = result.get("report_data", {}) or {}
    try:
        _, job_profiles, _, _ = _ensure_system()
    except Exception:
        job_profiles = {}
    return JSONResponse(
        {
            "student_profile": student_profile,
            "match_results": match_results,
            "career_path": _compact_career_path(result.get("career_path", {}), job_profiles),
            "action_plan": result.get("action_plan", {}),
            "report_data": _compact_report_data(rd),
            "report_for_export": _report_for_export(rd, job_profiles),
        }
    )


def _process_planning_fast(student_input: dict, components: tuple) -> dict:
    """稳定优先路径：尽量降低外部 LLM 波动对时延的影响。"""
    llm, job_profiles, career_graph, matching_engine = components
    from models.student_profile import StudentProfileAnalyzer
    from models.report_generator import CareerReportGenerator

    analyzer = StudentProfileAnalyzer(llm=None)
    mbti = (student_input.get("mbti_type") or "").strip()
    if student_input.get("resume_path"):
        student_profile = analyzer.analyze_from_resume(student_input["resume_path"], mbti_type=mbti)
    else:
        fd = dict(student_input.get("form_data") or {})
        if mbti:
            fd["mbti_type"] = mbti
        student_profile = analyzer.analyze_from_form(fd)

    top_k = student_input.get("top_k", 10)
    use_ai = bool(student_input.get("use_ai", False))
    match_results = matching_engine.recommend_top_jobs(
        student_profile, job_profiles, top_k=top_k, use_ai=use_ai
    )
    target_jobs = student_input.get("target_jobs") or []
    target_job = (match_results[0]["job_name"] if match_results else "") or (target_jobs[0] if target_jobs else "")

    # 报告生成也使用无 LLM 版本，避免网络波动影响响应时延
    report_gen = CareerReportGenerator(llm_wrapper=None)
    career_path = report_gen.generate_career_path_section(target_job, career_graph)
    top_match = match_results[0] if match_results else {}
    gap = top_match.get("gap_analysis", {})
    action_plan = report_gen.generate_action_plan(gap, target_job=target_job, top_match=top_match, timeline="6_months")
    executive_summary = report_gen.generate_executive_summary(top_match)
    report_data = report_gen.compile_full_report(
        student_profile,
        match_results,
        career_path,
        action_plan,
        executive_summary=executive_summary,
    )
    return {
        "student_profile": student_profile,
        "match_results": match_results,
        "career_path": career_path,
        "action_plan": action_plan,
        "report_data": report_data,
    }


def _ensure_system() -> tuple:
    global _SYSTEM_COMPONENTS
    if _SYSTEM_COMPONENTS is None:
        _SYSTEM_COMPONENTS = initialize_system()
    return _SYSTEM_COMPONENTS


def _ensure_llm_for_chat() -> Any:
    """仅创建 LLM 客户端，供 /api/chat 使用（与 initialize_system 解耦）。"""
    global _CHAT_LLM
    if _CHAT_LLM is None:
        from dotenv import load_dotenv

        load_dotenv()
        from models.llm_wrapper import LLMWrapper

        _CHAT_LLM = LLMWrapper(
            provider=os.getenv("LLM_PROVIDER", "qwen"),
            api_key=os.getenv("LLM_API_KEY", ""),
            model_name=os.getenv("LLM_MODEL_NAME", "qwen-max"),
            base_url=os.getenv(
                "LLM_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )
    return _CHAT_LLM


def _student_profile_to_dict(profile: Any) -> dict:
    preferences = getattr(profile, "career_preferences", {})
    skills_dict = getattr(profile, "skills", {})
    from models.mbti_mapping import get_mbti_label_zh

    mbti_raw = getattr(profile, "mbti_type", "") or ""
    return {
        "student_id": getattr(profile, "student_id", ""),
        "grade": preferences.get("grade", "") or "",
        "major_direction": preferences.get("major_direction", "") or "",
        "school_tier": getattr(profile, "school_tier", "") or "",
        "mbti_type": mbti_raw,
        "mbti_label_zh": get_mbti_label_zh(mbti_raw),
        "professional_skills": list(skills_dict.keys()) if isinstance(skills_dict, dict) else [],
        "certificates": getattr(profile, "certificates", []),
        "experience": getattr(profile, "experience", []),
        "awards_experience": getattr(profile, "awards", []),
        "research_experience": getattr(profile, "research", []),
        "learning_ability": getattr(profile, "learning_ability", 0),
        "communication": getattr(profile, "communication", 0),
        "stress_resistance": getattr(profile, "stress_resistance", 0),
        "innovation_ability": getattr(profile, "innovation_ability", 0),
        "teamwork": getattr(profile, "teamwork", 0),
        "problem_solving": getattr(profile, "problem_solving", 0),
        "technical_depth": getattr(profile, "technical_depth", 0),
        "target_industry": preferences.get("target_industry", []) or [],
        "target_city": preferences.get("target_city", "") or "",
        "completeness_score": getattr(profile, "completeness_score", 0),
        "competitiveness_score": getattr(profile, "competitiveness_score", 0),
    }


@app.post("/api/career-graph-visual")
def career_graph_visual(req: CareerGraphVisualRequest):
    """根据锚点岗位从全局职业图谱中抽取垂直晋升子图与换岗子图，并附带节点详情（含人岗雷达对比）。"""
    try:
        _, job_profiles, career_graph, _ = _ensure_system()
        export_fn = getattr(career_graph, "export_focus_visualization", None)
        if export_fn is None:
            return JSONResponse(
                {
                    "vertical": {"nodes": [], "edges": []},
                    "lateral": {"nodes": [], "edges": []},
                    "node_details": {},
                    "anchors_resolved": [],
                }
            )
        raw = export_fn(req.anchor_job_ids or [], computer_only=req.computer_only)
        sp_proxy = _student_proxy_for_radar(req.student_profile or {})
        node_ids: set[str] = set()
        for part in ("vertical", "lateral"):
            for n in raw.get(part, {}).get("nodes", []) or []:
                if isinstance(n, dict) and n.get("id"):
                    node_ids.add(str(n["id"]))
        # 垂直子图可含大量独立 job_id，全量雷达详情会拖慢接口；优先锚点再补足预算
        pref_ids: set[str] = set()
        for x in req.anchor_job_ids or []:
            if x is not None and str(x).strip():
                pref_ids.add(str(x).strip())
        for x in raw.get("anchors_resolved") or []:
            if x is not None and str(x).strip():
                pref_ids.add(str(x).strip())
        pref_ids &= node_ids
        rest_sorted = sorted(node_ids - pref_ids)
        detail_budget = 2800
        detail_ids = set(pref_ids)
        need = max(0, min(detail_budget, len(node_ids)) - len(detail_ids))
        detail_ids.update(rest_sorted[:need])
        details: dict[str, Any] = {}
        for nid in detail_ids:
            jp = job_profiles.get(nid)
            if jp is not None:
                details[nid] = _node_tooltip_payload(jp, sp_proxy)
        raw["node_details"] = details
        return JSONResponse(raw)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"career graph visual failed: {e}")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/chat")
def chat_consult(req: ChatConsultRequest):
    """实时职业咨询：多轮对话，由 LLM 给出建议；信息不足时引导追问。"""
    import json

    raw: list[dict[str, str]] = []
    for m in req.messages or []:
        text = (m.content or "").strip()
        if not text:
            continue
        raw.append({"role": m.role, "content": text})
    if not raw:
        raise HTTPException(status_code=400, detail="请至少发送一条用户消息。")
    if raw[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="最后一条须为用户消息。")
    try:
        llm = _ensure_llm_for_chat()
        reply = llm.career_consult_chat(raw)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"chat failed: {e}")
    if not reply:
        raise HTTPException(status_code=502, detail="模型返回为空。")
    stripped = reply.strip()
    if stripped.startswith("{") and '"error"' in stripped:
        try:
            err_obj = json.loads(stripped)
            if isinstance(err_obj, dict) and err_obj.get("error"):
                raise HTTPException(status_code=502, detail=str(err_obj["error"]))
        except json.JSONDecodeError:
            pass
    return {"reply": reply}


@app.get("/api/system-info")
def system_info():
    try:
        components = _ensure_system()
        _, job_profiles, _, _ = components
        return {"job_profile_count": len(job_profiles)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"system init failed: {e}")


@app.post("/api/plan")
def plan(req: PlanRequest):
    try:
        components = _ensure_system()
        mbti = (req.mbti_type or "").strip()
        fd = dict(req.form_data or {})
        if mbti:
            fd["mbti_type"] = mbti
        result = _process_planning_fast(
            {
                "form_data": fd,
                "resume_path": req.resume_path,
                "target_jobs": req.target_jobs or [],
                "top_k": req.top_k,
                "use_ai": req.use_ai,
                "mbti_type": mbti,
            },
            components,
        )
        return _pack_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"planning failed: {e}")


@app.post("/api/plan-resume")
async def plan_resume(
    file: UploadFile = File(...),
    top_k: int = Form(10),
    use_ai: bool = Form(False),
    mbti_type: str = Form(""),
):
    tmp_path = None
    try:
        suffix = Path(file.filename or "").suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        components = _ensure_system()
        mbti = (mbti_type or "").strip()
        result = _process_planning_fast(
            {"resume_path": tmp_path, "top_k": top_k, "use_ai": use_ai, "mbti_type": mbti},
            components,
        )
        return _pack_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"resume planning failed: {e}")
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


@app.get("/")
def index():
    """Return frontend home page."""
    home_path = _FRONTEND_DIR / "index.html"
    if home_path.exists():
        return FileResponse(str(home_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Frontend home page not found. Please create frontend/index.html"})


@app.get("/profile-detail")
def profile_detail():
    """Return profile detail page."""
    page_path = _FRONTEND_DIR / "profile-detail.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Profile detail page not found"})


@app.get("/job-profile")
def job_profile():
    """Return job profile page."""
    page_path = _FRONTEND_DIR / "job-profile.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Job profile page not found"})


@app.get("/student-profile-analysis")
def student_profile_analysis():
    """Return student profile analysis page."""
    page_path = _FRONTEND_DIR / "student-profile-analysis.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Student profile analysis page not found"})


@app.get("/vertical-job-graph")
def vertical_job_graph_page():
    """垂直岗位图谱与换岗路径可视化页。"""
    page_path = _FRONTEND_DIR / "vertical-job-graph.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "vertical-job-graph.html not found"})


@app.post("/api/export-word")
def export_word(payload: dict = Body(...)):
    try:
        from models.report_generator import CareerReportGenerator

        rd = payload.get("report") or payload.get("report_for_export") or payload
        if not isinstance(rd, dict) or not rd.get("title"):
            raise HTTPException(status_code=400, detail="Missing report data. Please generate plan result first.")
        out_dir = _BASE_DIR / "data" / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "career_report_export.docx"
        gen = CareerReportGenerator(llm_wrapper=None)
        if not gen.export_to_word(rd, str(out_path)):
            raise HTTPException(status_code=500, detail="Word export failed")
        return FileResponse(
            str(out_path),
            filename="career_report.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"export word failed: {e}")


@app.post("/api/export-pdf")
def export_pdf(payload: dict = Body(...)):
    try:
        from models.report_generator import CareerReportGenerator

        rd = payload.get("report") or payload.get("report_for_export") or payload
        if not isinstance(rd, dict) or not rd.get("title"):
            raise HTTPException(status_code=400, detail="Missing report data. Please generate plan result first.")
        out_dir = _BASE_DIR / "data" / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "career_report_export.pdf"
        gen = CareerReportGenerator(llm_wrapper=None)
        if not gen.export_to_pdf(rd, str(out_path)):
            raise HTTPException(status_code=500, detail="PDF export failed (check Chinese font availability)")
        return FileResponse(
            str(out_path),
            filename="career_report.pdf",
            media_type="application/pdf",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"export pdf failed: {e}")


@app.get("/new-home")
def new_home():
    """Preview frontend home page."""
    home_path = _FRONTEND_DIR / "index.html"
    if home_path.exists():
        return FileResponse(str(home_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Frontend home page not found. Please create frontend/index.html"})


@app.get("/profile")
def profile_page():
    """Return profile form page."""
    page_path = _FRONTEND_DIR / "profile.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Profile form page not found"})


@app.get("/report")
def report_page():
    """Return report generation page."""
    page_path = _FRONTEND_DIR / "report.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Report page not found"})


@app.get("/consult")
def consult_page():
    """AI 实时职业咨询页。"""
    page_path = _FRONTEND_DIR / "consult.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Consult page not found"})


@app.get("/resume")
def resume_page():
    """Return resume upload page."""
    page_path = _FRONTEND_DIR / "resume.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Resume page not found"})


@app.get("/info-recruit")
def info_recruit_page():
    """Return recruit calendar page."""
    page_path = _FRONTEND_DIR / "info-recruit.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Recruit calendar page not found"})


@app.get("/info-industry")
def info_industry_page():
    """Return industry insight page."""
    page_path = _FRONTEND_DIR / "info-industry.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Industry insight page not found"})


@app.get("/info-resources")
def info_resources_page():
    """Return resources page."""
    page_path = _FRONTEND_DIR / "info-resources.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Resources page not found"})


@app.get("/growth-communication")
def growth_communication_page():
    """Return communication page."""
    page_path = _FRONTEND_DIR / "growth-communication.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Communication page not found"})


@app.get("/growth-resume-tips")
def growth_resume_tips_page():
    """Return resume tips page."""
    page_path = _FRONTEND_DIR / "growth-resume-tips.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Resume tips page not found"})


@app.get("/growth-wellbeing")
def growth_wellbeing_page():
    """Return wellbeing page."""
    page_path = _FRONTEND_DIR / "growth-wellbeing.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Wellbeing page not found"})


@app.get("/growth-study")
def growth_study_page():
    """Return study management page."""
    page_path = _FRONTEND_DIR / "growth-study.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Study management page not found"})


@app.get("/growth-family")
def growth_family_page():
    """Return family communication page."""
    page_path = _FRONTEND_DIR / "growth-family.html"
    if page_path.exists():
        return FileResponse(str(page_path), media_type="text/html; charset=utf-8")
    return JSONResponse({"message": "Family communication page not found"})


if __name__ == "__main__":
    import threading
    import uvicorn
    import webbrowser

    def _open_homepage() -> None:
        try:
            webbrowser.open("http://127.0.0.1:8000/new-home")
        except Exception:
            pass

    # 延迟一点再打开，避免服务尚未监听时浏览器提前访问失败。
    threading.Timer(1.0, _open_homepage).start()

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True, access_log=False)


