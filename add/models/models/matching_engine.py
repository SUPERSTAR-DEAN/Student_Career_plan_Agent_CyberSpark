# -*- coding: utf-8 -*-
"""人岗智能匹配引擎（四大维度加权，关键技能匹配准确率≥80%）"""
from __future__ import annotations

from typing import Any, Optional

from config import AppConfig

class MatchingEngine:
    """人岗智能匹配引擎：基础要求、职业技能、职业素养、发展潜力"""

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or dict(AppConfig.MATCH_WEIGHTS)

    def calculate_dimension_score(
        self,
        student_dim: dict,
        job_dim: dict,
        dimension: str,
    ) -> float:
        """计算单维度匹配得分 0-100"""
        if dimension == "basic_requirements":
            return _score_basic(student_dim, job_dim)
        if dimension == "professional_skills":
            return _score_professional_skills(student_dim, job_dim)
        if dimension == "professional_quality":
            return _score_quality(student_dim, job_dim)
        if dimension == "development_potential":
            return _score_potential(student_dim, job_dim)
        return 50.0

    def calculate_overall_match(
        self,
        student_profile: Any,
        job_profile: Any,
        gap_analysis: Optional[dict] = None,
        use_ai: bool = True # 你有报告就给我，没有我就帮你生成。
    ) -> dict:
        """计算综合匹配度及各维度得分；可传入预计算的 gap_analysis"""
        # 正确写法（不用字符串，不报错）
        student_dim = getattr(student_profile, "to_dimension_dict", lambda: {})()
        job_dim = getattr(job_profile, "to_dimension_dict", lambda: {})()

        dimension_scores = {}
        for dim_name in self.weights:
            sd = student_dim.get(dim_name, {})
            jd = job_dim.get(dim_name, {})
            dimension_scores[dim_name] = round(self.calculate_dimension_score(sd, jd, dim_name), 1)

        overall = sum(
            self.weights.get(d, 0) * dimension_scores.get(d, 50)
            for d in self.weights
        )
        overall = round(min(100.0, max(0.0, overall)), 1)

        # ========================
        # AI 生成【双格式】差距分析报告
        # 前端可自由切换：富文本报告 / 结构化模块
        # ========================
        if gap_analysis is None:
            if use_ai:
                # ----------------------
                # 原来的 AI 生成逻辑
                # ----------------------
                from models.llm_wrapper import LLMWrapper
                from dotenv import load_dotenv
                import os
                load_dotenv()

                llm = LLMWrapper(
                    api_key=os.getenv("LLM_API_KEY"),
                    base_url=os.getenv("LLM_BASE_URL"),
                    model_name=os.getenv("LLM_MODEL_NAME")
                )

                gap_analysis = llm.generate_dual_format_gap_report(
                    student_dim=student_dim,
                    job_dim=job_dim,
                    dimension_scores=dimension_scores,
                    overall_score=overall
                )
            else:
                # ======================
                # ✅ 直接调用你写好的 gap_analysis 函数
                # ======================
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent.parent))

                from models.student_profile import StudentProfileAnalyzer
                analyzer = StudentProfileAnalyzer()
                raw_gap = analyzer.gap_analysis(student_profile, job_profile)
                
                # 包装成和 AI 一样的格式（前端不用改）
                gap_analysis = {
                    "text": f"综合匹配度 {overall} 分\n缺失技能：{raw_gap['missing_skills']}\n缺失证书：{raw_gap['missing_certificates']}",
                    "structured": raw_gap
                }

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
    ) -> list[dict]:
        """推荐匹配度最高的前 K 个岗位"""
        results = []
        for jid, jp in job_profiles.items():
            r = self.calculate_overall_match(student_profile, jp)
            r["job_id"] = jid
            r["job_name"] = getattr(jp, "job_name", jid)
            results.append(r)
        results.sort(key=lambda x: -x["overall_score"])
        return results[:top_k]


def _score_basic(student_dim: dict, job_dim: dict) -> float:
    """基础要求得分（0-100）

    关键改动：去掉原先“无证书/无经历也有较高底分”的问题，
    改为根据岗位是否提出“证书/实习要求”来计算，同时技术深度也会参与，
    这样自评很低时不应仍得到很高分。
    """
    # 取岗位要求
    job_basic = job_dim.get("basic_requirements") if isinstance(job_dim, dict) else {}
    if not job_basic:
        job_basic = job_dim

    stu_basic = student_dim.get("basic_requirements") if isinstance(student_dim, dict) else {}
    if not stu_basic:
        stu_basic = student_dim

    job_certs = _list_from(job_basic, "certificates")
    stu_certs = _list_from(stu_basic, "certificates")

    job_exp_req = job_basic.get("internship_experience")  # 字符串/列表/空
    stu_exp = _list_from(stu_basic, "internship_experience")

    # 技术深度：学生侧为 1-5
    stu_td = stu_basic.get("technical_depth")
    td_score = min(100.0, (float(stu_td) / 5.0) * 100.0) if isinstance(stu_td, (int, float)) else 50.0
    
    # ========================
    # AI 智能判断证书匹配率
    # ========================
    from models.llm_wrapper import LLMWrapper
    from dotenv import load_dotenv
    import os

    load_dotenv()
    llm = LLMWrapper(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model_name=os.getenv("LLM_MODEL_NAME")
    )

    # AI 判断
    cert_result = llm.match_certificates(stu_certs, job_certs)
    cert_score = cert_result.get("match_rate", 50)

    # ======================
    # AI 智能判断实习匹配度
    # ======================
    has_job_exp_req = bool(job_exp_req) and str(job_exp_req).strip() != ""

    if has_job_exp_req:
        # ✅ 这里和上面证书保持一样，都用 llm.xxx
        ai_result = llm.match_internship(stu_exp, job_exp_req)
        exp_score = float(ai_result.get("match_rate", 50))
    else:
        exp_score = 50.0

    # 加权合成
    score = 0.25 * cert_score + 0.4 * exp_score + 0.35 * td_score
    return round(min(100.0, max(0.0, score)), 1)


def _score_professional_skills(student_dim: dict, job_dim: dict) -> float:
    """职业技能匹配得分（0-100）：使用千问AI智能判断技能匹配度"""
    # 取数据
    job_skills = job_dim.get("professional_skills_list") or _list_from(job_dim.get("professional_skills"), "skills")
    stu_skills_raw = student_dim.get("professional_skills", {})

    # 格式化学生技能
    if isinstance(stu_skills_raw, list):
        stu_skills = stu_skills_raw
    elif isinstance(stu_skills_raw, dict):
        stu_skills = [f"{k}（掌握程度：{v}）" for k, v in stu_skills_raw.items()]
    else:
        stu_skills = []

    # 岗位无技能要求 → 给基准分
    if not job_skills:
        return 50.0

    # ========================
    # 千问AI判断职业技能匹配率
    # ========================
    from models.llm_wrapper import LLMWrapper
    from dotenv import load_dotenv
    import os

    load_dotenv()
    llm = LLMWrapper(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model_name=os.getenv("LLM_MODEL_NAME")
    )

    ai_result = llm.match_skills(stu_skills, job_skills)
    skill_score = float(ai_result.get("match_rate", 50))

    return round(min(100.0, max(0.0, skill_score)), 1)

def _score_quality(student_dim: dict, job_dim: dict) -> float:
    """职业素养得分（0-100）：使用千问AI判断软素质匹配度"""
    # 取出岗位要求 & 学生素养
    job_quality = job_dim.get("professional_quality") if isinstance(job_dim, dict) else {}
    if not job_quality:
        job_quality = job_dim

    stu_quality = student_dim.get("professional_quality") if isinstance(student_dim, dict) else {}
    if not stu_quality:
        stu_quality = student_dim

    # 如果岗位没有提出任何素养要求 → 直接返回中性分50
    quality_keys = ["communication", "teamwork", "stress_resistance", "problem_solving"]
    has_job_requirement = False
    for k in quality_keys:
        jv = job_quality.get(k)
        if jv is not None and str(jv).strip() != "":
            has_job_requirement = True
            break

    if not has_job_requirement:
        return 50.0

    # ========================
    # 千问AI判断职业素养匹配率
    # ========================
    from models.llm_wrapper import LLMWrapper
    from dotenv import load_dotenv
    import os

    load_dotenv()
    llm = LLMWrapper(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model_name=os.getenv("LLM_MODEL_NAME")
    )

    ai_result = llm.match_quality(stu_quality, job_quality)
    quality_score = float(ai_result.get("match_rate", 50))

    return round(min(100.0, max(0.0, quality_score)), 1)


def _score_potential(student_dim: dict, job_dim: dict) -> float:
    """发展潜力得分（0-100）：使用千问AI判断学习能力与创新能力匹配度"""
    # 取出岗位要求 & 学生潜力
    job_potential = job_dim.get("development_potential") if isinstance(job_dim, dict) else {}
    if not job_potential:
        job_potential = job_dim

    stu_potential = student_dim.get("development_potential") if isinstance(student_dim, dict) else {}
    if not stu_potential:
        stu_potential = student_dim

    # 判断岗位是否明确要求学习能力 / 创新能力
    keys = ["learning_ability", "innovation_ability"]
    has_job_requirement = False
    for k in keys:
        jv = job_potential.get(k)
        if jv is not None and str(jv).strip() != "":
            has_job_requirement = True
            break

    # 岗位无要求 → 返回统一中性分 50
    if not has_job_requirement:
        return 50.0

    # ========================
    # 千问AI判断潜力匹配率
    # ========================
    from models.llm_wrapper import LLMWrapper
    from dotenv import load_dotenv
    import os

    load_dotenv()
    llm = LLMWrapper(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model_name=os.getenv("LLM_MODEL_NAME")
    )

    ai_result = llm.match_potential(stu_potential, job_potential)
    potential_score = float(ai_result.get("match_rate", 50))

    return round(min(100.0, max(0.0, potential_score)), 1)

def _list_from(d: Any, key: str) -> list:
    if d is None:
        return []
    v = d.get(key)
    if isinstance(v, list):
        return v
    if v is not None:
        return [str(v)]
    return []

# def _str_or_list(v: Any) -> list:
#     if v is None:
#         return []
#     if isinstance(v, list):
#         return v
#     return [str(v)] if str(v).strip() else []

# def _fuzzy_in(needle: str, hay: list) -> bool:
#     n = (needle or "").lower()
#     for h in hay or []:
#         if n in (str(h).lower()) or (str(h).lower() in n):
#             return True
#     return False

# def _simple_gap(student_profile: Any, job_profile: Any) -> dict:
#     try:
#         from models.student_profile import StudentProfileAnalyzer
#         return StudentProfileAnalyzer().gap_analysis(student_profile, job_profile)
#     except Exception:
#         return {"missing_skills": [], "to_improve": {}, "advantage_skills": []}
