# -*- coding: utf-8 -*-
"""人岗智能匹配引擎（六大维度加权；可选大模型子维度打分）"""
from __future__ import annotations

import re
import zlib
from typing import Any, Optional

from config import AppConfig


def _normalize_job_title(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "").replace("\u3000", "")


def _normalize_company(name: str) -> str:
    return (name or "").strip().lower()[:80]


def _count_matched_skills(student_profile: Any, job_skills: list) -> tuple[int, int]:
    """岗位技能列表与学生技能的命中数、岗位技能条数（用于排序与去重展示）。"""
    st = getattr(student_profile, "skills", None) or {}
    if not isinstance(st, dict):
        st = {}
    req = [str(x).strip() for x in (job_skills or []) if x and str(x).strip()]
    if not req:
        return 0, 0
    hits = 0
    for js in req:
        sk = js.lower()
        found = False
        for k in st:
            kl = (k or "").strip().lower()
            if not kl:
                continue
            if sk == kl or sk in kl or kl in sk:
                found = True
                break
        if found:
            hits += 1
    return hits, len(req)


_SKILL_CANON_MAP = {
    "c++": "cpp",
    "cplusplus": "cpp",
    "cpp": "cpp",
    "c/c++": "cpp",
    "c语言": "c",
    "clang": "c",
    "java": "java",
    "python": "python",
    "golang": "go",
    "go": "go",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
}


def _canon_skill_name(s: str) -> str:
    t = (s or "").strip().lower().replace(" ", "")
    return _SKILL_CANON_MAP.get(t, t)


def _extract_language_set(items: list[str]) -> set[str]:
    langs: set[str] = set()
    for x in items or []:
        c = _canon_skill_name(str(x))
        if c in {"cpp", "c", "java", "python", "go", "javascript", "typescript"}:
            langs.add(c)
    return langs


def _language_gap_penalty(student_profile: Any, jp: Any) -> float:
    """
    若岗位明确要求语言栈且学生未覆盖，则进行硬惩罚。
    惩罚值用于最终 overall_score 调整，提升区分度与准确性。
    """
    req = getattr(jp, "required_skills", None) or []
    req_langs = _extract_language_set([str(x) for x in req])
    title = str(getattr(jp, "job_name", "") or "").lower()
    if "c++" in title or "c/c++" in title:
        req_langs.add("cpp")
    if "java" in title:
        req_langs.add("java")
    if "python" in title:
        req_langs.add("python")
    if not req_langs:
        return 0.0
    st = getattr(student_profile, "skills", None) or {}
    stu_langs = _extract_language_set([str(k) for k in st.keys()] if isinstance(st, dict) else [])
    miss = len(req_langs - stu_langs)
    if miss <= 0:
        return 0.0
    # 缺 1 种核心语言约扣 8 分，缺 2 种约扣 13 分，上限 15
    return min(15.0, 3.0 + 5.0 * miss)


def _infer_job_track(jp: Any, required_skills: list[str]) -> str:
    """按岗位标题/描述/技能粗分轨道，提升同类岗位内外的区分度。"""
    title = str(getattr(jp, "job_name", "") or "").lower()
    desc = str(getattr(jp, "description", "") or "").lower()
    text = f"{title}\n{desc}\n" + " ".join(str(x).lower() for x in (required_skills or []))
    if any(k in text for k in ("科研", "研究员", "算法研究", "论文", "实验室", "research")):
        return "research"
    if any(k in text for k in ("前端", "react", "vue", "javascript", "typescript", "web")):
        return "frontend"
    if any(k in text for k in ("后端", "服务端", "spring", "fastapi", "django", "golang", "java开发")):
        return "backend"
    if any(k in text for k in ("数据库", "dba", "mysql", "oracle", "postgresql", "sql优化", "索引")):
        return "database"
    if any(k in text for k in ("数据开发", "数据工程", "etl", "hadoop", "spark", "flink", "数仓", "kafka")):
        return "data"
    return "general"


def _track_specific_adjustment(student_profile: Any, jp: Any, required_skills: list[str]) -> float:
    """
    岗位轨道化加减分：
    - 命中轨道核心能力给奖励
    - 缺少轨道关键能力给惩罚
    目标：让“科研/前端/后端/数据库/数据开发”分布更合理，减少同质化。
    """
    track = _infer_job_track(jp, required_skills)
    st = getattr(student_profile, "skills", None) or {}
    stu_skills = [str(k).lower() for k in st.keys()] if isinstance(st, dict) else []
    exp_text = " ".join(str(x).lower() for x in (getattr(student_profile, "experience", None) or []))
    awards_text = " ".join(str(x).lower() for x in (getattr(student_profile, "awards", None) or []))
    research_text = " ".join(str(x).lower() for x in (getattr(student_profile, "research", None) or []))
    all_text = " ".join(stu_skills) + " " + exp_text + " " + awards_text + " " + research_text

    def hit_any(keywords: list[str]) -> int:
        return sum(1 for k in keywords if k and k in all_text)

    if track == "frontend":
        keys = ["javascript", "typescript", "react", "vue", "html", "css"]
        h = hit_any(keys)
        if h == 0:
            return -9.0
        return min(6.0, h * 1.2 - 1.0)
    if track == "backend":
        keys = ["java", "spring", "python", "django", "flask", "fastapi", "go", "mysql", "redis"]
        h = hit_any(keys)
        if h <= 1:
            return -8.0
        return min(6.5, h * 0.9 - 0.8)
    if track == "database":
        keys = ["sql", "mysql", "oracle", "postgresql", "索引", "事务", "数据库"]
        h = hit_any(keys)
        if h == 0:
            return -10.0
        return min(6.5, h * 1.3 - 1.2)
    if track == "data":
        keys = ["sql", "hadoop", "spark", "flink", "etl", "kafka", "数据仓库", "数仓"]
        h = hit_any(keys)
        if h == 0:
            return -9.5
        return min(6.5, h * 1.1 - 1.0)
    if track == "research":
        # 科研岗强调论文/科研经历，不能只靠编程语言拿高分
        h_skill = hit_any(["机器学习", "深度学习", "tensorflow", "pytorch", "算法", "数学"])
        h_research = hit_any(["论文", "科研", "课题", "专利", "实验"])
        if h_skill == 0 and h_research == 0:
            return -11.0
        if h_research == 0:
            return -6.0 + min(2.0, h_skill * 0.5)
        return min(7.5, h_research * 2.2 + h_skill * 0.6 - 1.0)
    return 0.0


def _student_level_for_job_skill(st: dict, job_skill: str) -> int:
    """学生侧对某一岗位技能词的最大自评等级 0~5。"""
    sk = (job_skill or "").strip().lower()
    if not sk:
        return 0
    best = 0
    for k, v in st.items():
        kl = (k or "").strip().lower()
        if not kl:
            continue
        if sk == kl or sk in kl or kl in sk:
            try:
                lv = int(v)
            except (TypeError, ValueError):
                lv = 0
            best = max(best, max(0, min(5, lv)))
    return best


def _student_search_blob(student_profile: Any) -> str:
    """学生侧可检索文本：技能、经历、偏好等，用于与岗位文本算契合度。"""
    parts: list[str] = []
    sk = getattr(student_profile, "skills", None) or {}
    if isinstance(sk, dict):
        parts.extend(str(k) for k in sk.keys())
    for attr in ("experience", "awards", "research"):
        parts.extend(str(x) for x in (getattr(student_profile, attr, None) or []))
    prefs = getattr(student_profile, "career_preferences", None) or {}
    if isinstance(prefs, dict):
        for key in ("major_direction", "target_industry", "target_city", "grade", "interests"):
            v = prefs.get(key)
            if isinstance(v, list):
                parts.extend(str(x) for x in v)
            elif v is not None and str(v).strip():
                parts.append(str(v))
    return " ".join(parts).lower()


def _job_search_blob(jp: Any) -> str:
    parts = [str(getattr(jp, "job_name", "") or ""), str(getattr(jp, "description", "") or "")]
    parts.extend(str(x) for x in (getattr(jp, "required_skills", None) or []))
    return " ".join(parts).lower()


def _ngram_tokens(s: str, n: int = 2) -> set[str]:
    s = re.sub(r"\s+", "", (s or "").lower())
    out: set[str] = set()
    if len(s) >= n:
        for i in range(len(s) - n + 1):
            out.add(s[i : i + n])
    for m in re.findall(r"[a-z0-9+#./]{2,}", s):
        if len(m) <= 28:
            out.add(m)
    return out


def _lexical_fit_ratio(student_profile: Any, jp: Any) -> float:
    """学生画像文本与岗位名称/描述/技能列表的契合度 0~1，用于拉开不同岗位的维度分。"""
    st = _student_search_blob(student_profile)
    jb = _job_search_blob(jp)
    ts, tj = _ngram_tokens(st), _ngram_tokens(jb)
    if not tj:
        return 0.28
    inter = len(ts & tj)
    union = len(ts | tj)
    jacc = inter / union if union else 0.0
    cov = inter / max(8, len(tj))
    return max(0.0, min(1.0, 0.45 * jacc + 0.55 * cov))


def _dim_lex_sensitivity(dim_name: str) -> float:
    """各维对「人岗文本契合」的响应权重，职业技能略高、基础次之。"""
    return {
        "professional_skills": 1.12,
        "basic_requirements": 0.78,
        "communication_teamwork": 0.52,
        "stress_problem_solving": 0.52,
        "learning_ability": 0.62,
        "innovation_ability": 0.58,
    }.get(dim_name, 0.55)


def _dim_micro_spread(job_id: str, dim_name: str) -> float:
    """同一学生在不同岗位、同一岗位不同维度上的确定性微差，避免列表里六维全等。"""
    key = f"{job_id or 'unknown'}\x1f{dim_name}"
    h = zlib.adler32(key.encode("utf-8", errors="ignore")) & 0xFFFFFFFF
    return (h % 2401) / 2401.0 * 3.6 - 1.8


def _list_display_adjustment(student_profile: Any, jp: Any, required_skills: list) -> float:
    """
    在六维基础分之上叠加「技能掌握深度 + 岗位文本/行业等指纹」，避免 Top 列表大量同分。
    上限约 4.5，再与基础分相加后封顶 100。
    """
    st = getattr(student_profile, "skills", None) or {}
    if not isinstance(st, dict):
        st = {}
    req = [str(x).strip() for x in (required_skills or []) if x and str(x).strip()]
    nreq = max(1, len(req))

    level_sum = 0.0
    for js in req:
        level_sum += float(_student_level_for_job_skill(st, js))
    depth = level_sum / (5.0 * nreq)

    hits, _ = _count_matched_skills(student_profile, required_skills)
    coverage = hits / nreq

    desc = (getattr(jp, "description", "") or "")[:4000]
    desc_len = len(desc)
    ind = (getattr(jp, "industry", "") or "")[:80]
    loc = (getattr(jp, "location", "") or "")[:80]
    sal = (getattr(jp, "salary_range", "") or "")[:60]
    cid = str(getattr(jp, "job_id", ""))
    comp = (getattr(jp, "company_name", "") or "")[:100]
    title = (getattr(jp, "job_name", "") or "")[:80]
    cert_n = len(getattr(jp, "certificates", None) or [])
    noise_key = f"{cid}\x1f{comp}\x1f{title}\x1f{ind}\x1f{loc}\x1f{sal}\x1f{desc_len}\x1f{nreq}\x1f{cert_n}"
    h = zlib.adler32(noise_key.encode("utf-8", errors="ignore")) & 0xFFFFFFFF
    h_norm = (h % 20000) / 200000.0

    bonus = (
        depth * 2.4
        + coverage * 0.62
        + min(desc_len, 4000) / 22000.0
        + min(cert_n, 8) / 180.0
        + h_norm * 1.35
    )
    return min(6.2, bonus)


def _stu_level_pct(v: Any, default: float = 42.0) -> float:
    try:
        x = int(v)
        if 1 <= x <= 5:
            return (x - 1) / 4.0 * 100.0
    except (TypeError, ValueError):
        pass
    return default


def _radar_student_series(sp: Any) -> list[float]:
    """学生侧七维能力估计 0~100，供岗位画像页雷达图「学生」折线。"""
    skills = getattr(sp, "skills", None) or {}
    if isinstance(skills, dict) and skills:
        levels: list[int] = []
        for v in skills.values():
            try:
                levels.append(max(0, min(5, int(v))))
            except (TypeError, ValueError):
                levels.append(0)
        prof = sum(levels) / len(levels) / 5.0 * 100.0 if levels else 30.0
    else:
        prof = 28.0
    exps = getattr(sp, "experience", None) or []
    intern = min(100.0, 16.0 + float(len(exps)) * 21.0)
    comm = _stu_level_pct(getattr(sp, "communication", 0))
    stress = _stu_level_pct(getattr(sp, "stress_resistance", 0))
    learn = _stu_level_pct(getattr(sp, "learning_ability", 0), 44.0)
    innov = _stu_level_pct(getattr(sp, "innovation_ability", 0), 40.0)
    certs = getattr(sp, "certificates", None) or []
    cert_sc = min(100.0, float(len(certs)) * 26.0)
    return [
        round(prof, 1),
        round(intern, 1),
        round(comm, 1),
        round(stress, 1),
        round(learn, 1),
        round(innov, 1),
        round(cert_sc, 1),
    ]


def _radar_job_required_series(sp: Any, jp: Any) -> list[float]:
    """岗位期望七维 0~100，雷达图「岗位要求」折线；结合 JD 与学生现状拉开差距。"""
    stu = _radar_student_series(sp)
    desc = ((getattr(jp, "description", "") or "") + "\n" + (getattr(jp, "job_name", "") or "")).lower()
    req_skills = getattr(jp, "required_skills", None) or []
    n_req = max(1, len(req_skills))
    raw_prof = min(
        94.0,
        66.0 + min(24.0, float(n_req) * 1.7) + (5.0 if any(k in desc for k in ("架构", "资深", "高级", "专家")) else 0.0),
    )
    raw_intern = 80.0 if any(k in desc for k in ("实习", "经验", "项目", "工作")) else 65.0
    raw_comm = 78.0 + (8.0 if any(k in desc for k in ("沟通", "表达", "协调", "汇报")) else 0.0)
    raw_stress = 76.0 + (9.0 if any(k in desc for k in ("抗压", "压力", "高强度", "节奏")) else 0.0)
    raw_learn = 78.0 + (7.0 if any(k in desc for k in ("学习", "成长", "新技术", "自学")) else 0.0)
    raw_innov = 76.0 + (9.0 if any(k in desc for k in ("创新", "研发", "算法", "科研", "专利")) else 0.0)
    job_certs = getattr(jp, "certificates", None) or []
    raw_cert = min(92.0, 54.0 + float(len(job_certs)) * 8.5)
    raw = [raw_prof, raw_intern, raw_comm, raw_stress, raw_learn, raw_innov, raw_cert]
    jid = str(getattr(jp, "job_id", "") or "job")
    h = (zlib.adler32(jid.encode("utf-8", errors="ignore")) & 0xFFFF) % 19
    jitter = (h - 9) * 0.24
    out: list[float] = []
    for i, base in enumerate(raw):
        wobble = jitter * (0.65 if i % 2 == 0 else 1.05)
        tgt = max(base + wobble, stu[i] + 5.0)
        out.append(round(min(98.0, max(48.0, tgt)), 1))
    return out


def _four_dimension_bars(ds: dict[str, Any]) -> list[dict[str, Any]]:
    """四维匹配度条形图数据（与六维加权一致的可视聚合）。"""
    d = ds or {}
    basic = float(d.get("basic_requirements") or 0)
    skills = float(d.get("professional_skills") or 0)
    ct = float(d.get("communication_teamwork") or 0)
    sp = float(d.get("stress_problem_solving") or 0)
    quality = (ct + sp) / 2.0
    la = float(d.get("learning_ability") or 0)
    inn = float(d.get("innovation_ability") or 0)
    dev = (la + inn) / 2.0
    return [
        {"key": "basic", "name": "基础要求", "score": round(basic, 1), "color": "#ef4444"},
        {"key": "skills", "name": "职业技能", "score": round(skills, 1), "color": "#3b82f6"},
        {"key": "quality", "name": "职业素养", "score": round(quality, 1), "color": "#2563eb"},
        {"key": "potential", "name": "发展潜力", "score": round(dev, 1), "color": "#f97316"},
    ]


def _gap_suggestion_bullets(gap: dict, job_name: str, ds: dict[str, Any]) -> list[str]:
    """差距分析与建议：短列表文案，供岗位画像页展示。"""
    lines: list[str] = []
    ms = gap.get("missing_skills") or []
    if ms:
        tail = "、".join(str(x) for x in ms[:5])
        if len(ms) > 5:
            tail += " 等"
        lines.append(
            f"专业技能：岗位「{job_name}」强调 {tail}，建议对照 JD 制定补学路线（课程/项目/开源）并写入可验证经历。"
        )
    ti = gap.get("to_improve") or {}
    if isinstance(ti, dict) and ti:
        parts = []
        for k, v in list(ti.items())[:4]:
            try:
                parts.append(f"{k}（当前自评 {int(v)}/5）")
            except (TypeError, ValueError):
                parts.append(str(k))
        if parts:
            lines.append(
                "技能深度：以下项已达基础但与岗位要求仍有差距：" + "；".join(parts) + "。建议以作品或实习产出抬升到 4 分及以上。"
            )
    mc = gap.get("missing_certificates") or []
    if mc:
        lines.append("证书维度：可关注 " + "、".join(str(x) for x in mc[:6]) + " 等准入或加分项，结合目标城市校招要求备考。")
    adv = gap.get("advantage_skills") or []
    if adv:
        lines.append("可写进简历的优势技能：" + "、".join(str(x) for x in adv[:8]) + "，尽量用指标化成果描述。")
    for h in (gap.get("soft_dimension_hints") or [])[:5]:
        if isinstance(h, str) and h.strip():
            lines.append(h.strip())
    for c in (gap.get("core_strengths") or [])[:3]:
        if isinstance(c, str) and c.strip():
            lines.append(c.strip())
    ps = float(ds.get("professional_skills") or 0)
    if ps < 62 and not any("专业技能" in x for x in lines):
        lines.append(
            f"综合匹配上职业技能维度约 {ps:.0f} 分，与「{job_name}」核心栈重合有限，建议优先补齐岗位高频技能并做 1～2 个对口项目。"
        )
    if not lines:
        lines.append(
            f"建议结合「{job_name}」JD 做一次技能清单对照，把课程、竞赛、实习中与岗位相关的关键词显性写进简历。"
        )
    return lines[:12]


def _attach_job_profile_visuals(student_profile: Any, jp: Any, r: dict) -> None:
    """为岗位画像页附加雷达图、四维条形与建议列表（可 JSON 序列化）。"""
    ds = r.get("dimension_scores") or {}
    gap = r.get("gap_analysis") or {}
    job_name = str(r.get("job_name") or "").strip() or "目标岗位"
    r["radar_chart"] = {
        "labels": ["专业技能", "实习能力", "沟通能力", "抗压能力", "学习能力", "创新能力", "证书"],
        "student": _radar_student_series(student_profile),
        "job_required": _radar_job_required_series(student_profile, jp),
    }
    r["four_dimensions"] = _four_dimension_bars(ds)
    r["gap_suggestions"] = _gap_suggestion_bullets(gap, job_name, ds)


class MatchingEngine:
    """人岗智能匹配引擎：基础要求、职业技能、沟通协作、抗压与问题解决、学习与创新（六维）"""

    def __init__(self, weights: Optional[dict[str, float]] = None, llm: Any = None):
        self.weights = weights or dict(AppConfig.MATCH_WEIGHTS)
        self.llm = llm

    def _llm_ready(self) -> bool:
        return self.llm is not None and getattr(self.llm, "_client", None) is not None

    def calculate_dimension_score(
        self,
        student_dim: dict,
        job_dim: dict,
        dimension: str,
        *,
        use_ai: bool = False,
    ) -> float:
        """计算单维度匹配得分 0-100。基础/技能维传入对应子 dict；其余维请传入完整学生/岗位 dimension dict。"""
        llm = self.llm if use_ai and self._llm_ready() else None
        if dimension == "basic_requirements":
            return _score_basic(student_dim, job_dim, llm)
        if dimension == "professional_skills":
            return _score_professional_skills(student_dim, job_dim, llm)
        if dimension == "communication_teamwork":
            return _score_quality_keys(student_dim, job_dim, ["communication", "teamwork"], llm)
        if dimension == "stress_problem_solving":
            return _score_quality_keys(student_dim, job_dim, ["stress_resistance", "problem_solving"], llm)
        if dimension == "learning_ability":
            return _score_potential_key(student_dim, job_dim, "learning_ability", llm)
        if dimension == "innovation_ability":
            return _score_potential_key(student_dim, job_dim, "innovation_ability", llm)
        return 50.0

    def calculate_overall_match(
        self,
        student_profile: Any,
        job_profile: Any,
        gap_analysis: Optional[dict] = None,
        *,
        use_ai: bool = False,
    ) -> dict:
        """计算综合匹配度及各维度得分；可传入预计算的 gap_analysis"""
        student_dim = getattr(student_profile, "to_dimension_dict", lambda: {})()
        if not student_dim:
            student_dim = _profile_to_dim(student_profile)
        job_dim = getattr(job_profile, "to_dimension_dict", lambda: {})()
        if not job_dim:
            job_dim = _job_to_dim(job_profile)

        dimension_scores = {}
        for dim_name in self.weights:
            if dim_name in ("basic_requirements", "professional_skills"):
                sd = student_dim.get(dim_name, {})
                jd = job_dim.get(dim_name, {})
            else:
                sd, jd = student_dim, job_dim
            dimension_scores[dim_name] = round(
                self.calculate_dimension_score(sd, jd, dim_name, use_ai=use_ai), 1
            )

        # 规则匹配时大量岗位软技能模板相同，易导致各维分数完全一致；按人岗文本契合 + 岗位/维度指纹拉开显示分
        jid = str(getattr(job_profile, "job_id", "") or "")
        fit = _lexical_fit_ratio(student_profile, job_profile)
        for dim_name in list(dimension_scores.keys()):
            base = float(dimension_scores[dim_name])
            micro = _dim_micro_spread(jid, dim_name) * 0.42
            if use_ai:
                dimension_scores[dim_name] = round(
                    min(100.0, max(0.0, base + micro * 0.5)), 1
                )
            else:
                lex_adj = (fit - 0.30) * 5.8 * _dim_lex_sensitivity(dim_name)
                dimension_scores[dim_name] = round(
                    min(100.0, max(0.0, base + lex_adj + micro)), 1
                )

        overall = sum(
            self.weights.get(d, 0) * dimension_scores.get(d, 50)
            for d in self.weights
        )
        overall = round(min(100.0, max(0.0, overall)), 1)

        if gap_analysis is None:
            gap_analysis = _build_gap_analysis(
                self,
                student_profile,
                job_profile,
                student_dim,
                job_dim,
                dimension_scores,
                overall,
                use_ai=use_ai,
            )

        return {
            "overall_score": overall,
            "dimension_scores": dimension_scores,
            "gap_analysis": gap_analysis,
        }

    def recommend_top_jobs(
        self,
        student_profile: Any,
        job_profiles: dict[str, Any],
        top_k: int = 10,
        *,
        use_ai: bool = False,
    ) -> list[dict]:
        """推荐匹配度最高的前 K 个岗位。

        同「职位名称 + 公司」去重；并限制同名岗与同一 job_track 在 TopK 中的占比，
        避免近万条 CSV 中大量「Java」等同名岗占满列表；分数保留小数避免并列。
        """
        results = []
        for jid, jp in job_profiles.items():
            r = self.calculate_overall_match(student_profile, jp, use_ai=use_ai)
            r["job_id"] = jid
            r["job_name"] = getattr(jp, "job_name", jid)
            r["job_description"] = getattr(jp, "description", "")
            r["company_name"] = getattr(jp, "company_name", "") or ""
            r["industry"] = getattr(jp, "industry", "") or ""

            job_dimensions = _job_to_dim(jp)
            r["basic_requirements"] = job_dimensions.get("basic_requirements", {})
            r["professional_skills"] = job_dimensions.get("professional_skills", {})
            r["professional_quality"] = job_dimensions.get("professional_quality", {})
            r["development_potential"] = job_dimensions.get("development_potential", {})
            r["required_skills"] = job_dimensions.get("professional_skills_list", [])

            hits, nreq = _count_matched_skills(student_profile, r["required_skills"])
            r["matched_skill_count"] = hits
            r["required_skill_count"] = nreq
            base = float(r["overall_score"])
            extra = _list_display_adjustment(student_profile, jp, r["required_skills"])
            penalty = _language_gap_penalty(student_profile, jp)
            track_adj = _track_specific_adjustment(student_profile, jp, r["required_skills"])
            r["job_track"] = _infer_job_track(jp, r["required_skills"])
            r["overall_score"] = round(min(100.0, max(0.0, base + extra - penalty + track_adj)), 3)

            _attach_job_profile_visuals(student_profile, jp, r)

            results.append(r)

        results.sort(
            key=lambda x: (
                -float(x["overall_score"]),
                -int(x.get("matched_skill_count", 0)),
                -len(x.get("job_description") or ""),
                str(x.get("job_id", "")),
            )
        )

        unique = _pick_diverse_recommendations(results, top_k)

        return unique[:top_k]


def _pick_diverse_recommendations(results: list[dict], top_k: int) -> list[dict]:
    """在分数排序基础上限制同名岗与同一轨道占比，避免 Top 列表被「Java」等高频标题占满。"""
    seen_key: set[tuple[str, str]] = set()
    title_norm_counts: dict[str, int] = {}
    track_counts: dict[str, int] = {}
    unique: list[dict] = []
    max_per_title = 2
    max_per_track = 4

    def try_add(r: dict, strict: bool) -> bool:
        key = (
            _normalize_job_title(str(r.get("job_name", ""))),
            _normalize_company(str(r.get("company_name", ""))),
        )
        if key in seen_key:
            return False
        tkey = _normalize_job_title(str(r.get("job_name", "")))
        tr = str(r.get("job_track") or "general")
        if strict:
            if title_norm_counts.get(tkey, 0) >= max_per_title:
                return False
            if track_counts.get(tr, 0) >= max_per_track:
                return False
        seen_key.add(key)
        title_norm_counts[tkey] = title_norm_counts.get(tkey, 0) + 1
        track_counts[tr] = track_counts.get(tr, 0) + 1
        unique.append(r)
        return True

    for r in results:
        if len(unique) >= top_k:
            break
        try_add(r, strict=True)

    if len(unique) < top_k:
        for r in results:
            if len(unique) >= top_k:
                break
            try_add(r, strict=False)

    for r in unique:
        name = str(r.get("job_name") or "").strip() or "岗位"
        comp = str(r.get("company_name") or "").strip()
        r["job_display_name"] = f"{name} · {comp}" if comp else name

    return unique


def _build_gap_analysis(
    engine: MatchingEngine,
    student_profile: Any,
    job_profile: Any,
    student_dim: dict,
    job_dim: dict,
    dimension_scores: dict,
    overall: float,
    *,
    use_ai: bool,
) -> dict:
    """规则化差距（供行动计划）；可选附加 AI 双格式报告字段。"""
    try:
        from models.student_profile import StudentProfileAnalyzer

        analyzer = StudentProfileAnalyzer(llm=None)
        base = analyzer.gap_analysis(student_profile, job_profile)
    except Exception:
        base = _simple_gap(student_profile, job_profile)

    if use_ai and engine._llm_ready():
        try:
            dual = engine.llm.generate_dual_format_gap_report(
                student_dim, job_dim, dimension_scores, overall
            )
            if isinstance(dual, dict):
                base = {
                    **base,
                    "gap_text_report": dual.get("text_report", ""),
                    "gap_structured": dual.get("structured") or {},
                }
        except Exception:
            pass
    return base


def _score_basic(student_dim: dict, job_dim: dict, llm: Any = None) -> float:
    """基础要求得分（0-100）：可选大模型判证书/实习匹配，否则规则打分。"""
    job_basic = job_dim.get("basic_requirements") if isinstance(job_dim, dict) else {}
    if not job_basic:
        job_basic = job_dim

    stu_basic = student_dim.get("basic_requirements") if isinstance(student_dim, dict) else {}
    if not stu_basic:
        stu_basic = student_dim

    job_certs = _list_from(job_basic, "certificates")
    stu_certs = _list_from(stu_basic, "certificates")

    job_exp_req = job_basic.get("internship_experience")
    stu_exp = _list_from(stu_basic, "internship_experience")

    stu_td = stu_basic.get("technical_depth")
    td_score = min(100.0, (float(stu_td) / 5.0) * 100.0) if isinstance(stu_td, (int, float)) else 50.0

    has_job_exp_req = bool(job_exp_req) and str(job_exp_req).strip() != ""

    if llm is not None:
        try:
            if job_certs:
                cert_result = llm.match_certificates(stu_certs, job_certs)
                cert_score = float(cert_result.get("match_rate", 50))
            else:
                cert_score = 50.0
            if has_job_exp_req:
                ai_result = llm.match_internship(stu_exp, str(job_exp_req))
                exp_score = float(ai_result.get("match_rate", 50))
            else:
                exp_score = 50.0
            score = 0.25 * cert_score + 0.4 * exp_score + 0.35 * td_score
            return round(min(100.0, max(0.0, score)), 1)
        except Exception:
            pass

    if job_certs:
        cert_match = sum(1 for c in job_certs if _fuzzy_in(c, stu_certs)) / len(job_certs)
        cert_score = cert_match * 100.0
    else:
        cert_score = 50.0

    if has_job_exp_req:
        exp_score = 100.0 if bool(stu_exp) else 20.0
    else:
        exp_score = 50.0

    score = 0.4 * cert_score + 0.3 * exp_score + 0.3 * td_score
    return round(min(100.0, max(0.0, score)), 1)


def _score_professional_skills(student_dim: dict, job_dim: dict, llm: Any = None) -> float:
    """职业技能匹配得分：可选大模型判定，否则关键词/集合规则。"""
    job_skills = job_dim.get("professional_skills_list") or _list_from(job_dim.get("professional_skills"), "skills")
    stu_skills_raw = student_dim.get("professional_skills", {})

    if isinstance(stu_skills_raw, list):
        stu_skills_list = stu_skills_raw
    elif isinstance(stu_skills_raw, dict):
        stu_skills_list = [f"{k}（掌握程度：{v}）" for k, v in stu_skills_raw.items()]
    else:
        stu_skills_list = []

    if llm is not None and job_skills:
        try:
            ai_result = llm.match_skills(stu_skills_list, job_skills)
            skill_score = float(ai_result.get("match_rate", 50))
            return round(min(100.0, max(0.0, skill_score)), 1)
        except Exception:
            pass

    if not job_skills:
        # 岗位技能缺失时给中性偏低分，避免与“技能明确且高度匹配”岗位同分
        return 50.0
    stu_skills = student_dim.get("professional_skills", {})
    job_raw = [str(x).strip() for x in (job_skills or []) if str(x).strip()]
    job_langs = _extract_language_set(job_raw)
    if isinstance(stu_skills, dict):
        stu_langs = _extract_language_set([str(k) for k in stu_skills.keys()])
    elif isinstance(stu_skills, list):
        stu_langs = _extract_language_set([str(k) for k in stu_skills])
    else:
        stu_langs = set()
    if isinstance(stu_skills, list):
        stu_set = set(s.lower().strip() for s in stu_skills)
        match_count = sum(
            1
            for s in job_skills
            if (s or "").lower().strip() in stu_set or any((s or "").lower() in k for k in stu_set)
        )
    else:
        stu_set = {k.lower().strip(): v for k, v in (stu_skills or {}).items()}
        match_count = 0
        for js in job_skills:
            js = (js or "").strip().lower()
            if not js:
                continue
            if js in stu_set:
                match_count += 1
                continue
            cjs = _canon_skill_name(js)
            if cjs in {"cpp", "c", "java", "python", "go", "javascript", "typescript"}:
                # 语言栈不使用宽松子串匹配，避免“Java≈C++”这类误判
                for sk in stu_set:
                    if _canon_skill_name(sk) == cjs:
                        match_count += 1
                        break
                continue
            for sk, _level in stu_set.items():
                # 通用技能才允许模糊匹配，且至少 3 字符，降低误匹配率
                if len(js) >= 3 and (js in sk or sk in js):
                    match_count += 1
                    break
    ratio = match_count / len(job_skills) if job_skills else 0
    score = 5 + ratio * 95
    # 岗位有明确语言要求但学生未覆盖时，技能维最高限制在 35 分
    if job_langs and not (job_langs & stu_langs):
        score = min(score, 35.0)
    return min(100.0, score)


def _score_quality_keys(
    student_dim: dict,
    job_dim: dict,
    keys: list[str],
    llm: Any = None,
) -> float:
    """职业素养子项：仅对指定 keys 在岗位画像中有要求时计分；与 _score_quality 规则一致。"""
    job_quality = job_dim.get("professional_quality") if isinstance(job_dim, dict) else {}
    if not job_quality:
        job_quality = job_dim
    stu_quality = student_dim.get("professional_quality") if isinstance(student_dim, dict) else {}
    if not stu_quality:
        stu_quality = student_dim

    has_job_requirement = False
    for k in keys:
        jv = job_quality.get(k)
        if jv is not None and str(jv).strip() != "":
            has_job_requirement = True
            break

    if not has_job_requirement:
        return 50.0

    if llm is not None:
        try:
            stu_f = {k: stu_quality.get(k) for k in keys}
            job_f = {k: job_quality.get(k) for k in keys}
            ai_result = llm.match_quality(stu_f, job_f)
            quality_score = float(ai_result.get("match_rate", 50))
            return round(min(100.0, max(0.0, quality_score)), 1)
        except Exception:
            pass

    included = []
    for k in keys:
        jv = job_quality.get(k)
        if jv is not None and str(jv).strip() != "":
            included.append(k)

    total = 0.0
    for k in included:
        sv = stu_quality.get(k)
        if isinstance(sv, (int, float)):
            total += min(100.0, (float(sv) / 5.0) * 100.0)
        else:
            total += 50.0

    score = total / len(included) if included else 50.0
    return round(min(100.0, max(0.0, score)), 1)


def _score_potential_key(student_dim: dict, job_dim: dict, key: str, llm: Any = None) -> float:
    """发展潜力中的单项（学习能力 / 创新能力）。"""
    job_potential = job_dim.get("development_potential") if isinstance(job_dim, dict) else {}
    if not job_potential:
        job_potential = job_dim
    stu_potential = student_dim.get("development_potential") if isinstance(student_dim, dict) else {}
    if not stu_potential:
        stu_potential = student_dim

    jv = job_potential.get(key)
    if jv is None or str(jv).strip() == "":
        return 50.0

    if llm is not None:
        try:
            stu_f = {key: stu_potential.get(key)}
            job_f = {key: job_potential.get(key)}
            ai_result = llm.match_potential(stu_f, job_f)
            potential_score = float(ai_result.get("match_rate", 50))
            return round(min(100.0, max(0.0, potential_score)), 1)
        except Exception:
            pass

    sv = stu_potential.get(key)
    if isinstance(sv, (int, float)):
        return round(min(100.0, max(0.0, (float(sv) / 5.0) * 100.0)), 1)
    return 50.0


def _list_from(d: Any, key: str) -> list:
    if d is None:
        return []
    v = d.get(key)
    if isinstance(v, list):
        return v
    if v is not None:
        return [str(v)]
    return []


def _fuzzy_in(needle: str, hay: list) -> bool:
    n = (needle or "").lower()
    for h in hay or []:
        if n in (str(h).lower()) or (str(h).lower() in n):
            return True
    return False


def _profile_to_dim(p: Any) -> dict:
    return getattr(p, "to_dimension_dict", lambda: {})()


def _job_to_dim(j: Any) -> dict:
    return getattr(j, "to_dimension_dict", lambda: {})()


def _simple_gap(student_profile: Any, job_profile: Any) -> dict:
    try:
        from models.student_profile import StudentProfileAnalyzer

        return StudentProfileAnalyzer(llm=None).gap_analysis(student_profile, job_profile)
    except Exception:
        return {
            "missing_skills": [],
            "to_improve": {},
            "advantage_skills": [],
            "missing_certificates": [],
            "core_strengths": [],
            "soft_dimension_hints": [],
        }
