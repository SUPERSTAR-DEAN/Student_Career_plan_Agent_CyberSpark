# -*- coding: utf-8 -*-
"""学生就业能力画像与分析器"""
from __future__ import annotations

from typing import Any


def _norm_score(v: Any) -> float:
    """将各种输入规范为 0~100 的分数"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        if v <= 1:
            return float(v) * 100
        return min(100.0, max(0.0, float(v)))
    return 0.0


def _level_to_score(v: Any) -> float:
    """1-5 等级转 0-100"""
    if v is None:
        return 0.0
    try:
        x = int(v)
        if 1 <= x <= 5:
            return (x - 1) / 4.0 * 100
    except (ValueError, TypeError):
        pass
    return 0.0


class StudentProfile:
    """学生就业能力画像（与岗位画像维度对齐）"""

    def __init__(self, student_id: str = ""):
        self.student_id = student_id or "anonymous"
        self.skills: dict[str, int] = {}  # 技能名 -> 掌握程度 1-5
        self.certificates: list[str] = []
        self.experience: list[str] = []  # 项目/实习经历描述
        self.awards: list[str] = []  # 竞赛/奖项经历（文本描述）
        self.research: list[str] = []  # 科研/论文/专利经历（文本描述）
        self.school_tier: str = ""  # 院校层次（独立字段，与 add 版一致）
        self.career_preferences: dict[str, Any] = {}
        self.competitiveness_score: float = 0.0
        self.completeness_score: float = 0.0
        self.mbti_type: str = ""  # 如 INFJ；与自评融合后写入 to_dimension_dict
        # 与岗位画像对齐的维度（1-5 或描述）
        self.innovation_ability: int = 0
        self.learning_ability: int = 0
        self.stress_resistance: int = 0
        self.communication: int = 0
        self.teamwork: int = 0
        self.problem_solving: int = 0
        self.technical_depth: int = 0

    def calculate_scores(self) -> None:
        """计算竞争力与完整度评分（与 add/models/student_profile 对齐：分项完整度 + 权重和为 1 的竞争力）"""
        dims = [
            self.innovation_ability,
            self.learning_ability,
            self.stress_resistance,
            self.communication,
            self.teamwork,
            self.problem_solving,
            self.technical_depth,
        ]

        # ----- 一、信息完整度（有则加分，封顶 100）-----
        completeness = 0.0
        if self.skills:
            completeness += 10
        if self.certificates:
            completeness += 10
        if self.experience:
            completeness += 10
        if self.awards:
            completeness += 10
        if self.research:
            completeness += 10
        if (self.school_tier or "").strip():
            completeness += 5
        if self.career_preferences:
            completeness += 10
        if (getattr(self, "mbti_type", "") or "").strip():
            completeness += 5
        filled = sum(1 for d in dims if d and d > 0)
        completeness += 5 * filled
        self.completeness_score = min(100.0, round(completeness, 1))

        # ----- 二、竞争力（子项均为 0~100，权重和 = 1.0）-----
        soft_score = sum(_level_to_score(d) for d in dims) / 7 if dims else 0.0

        if self.skills:
            avg_skill_level = sum(self.skills.values()) / len(self.skills)
            skill_score = (avg_skill_level - 1) / 4.0 * 100.0
        else:
            skill_score = 0.0

        cert_score = min(15.0, len(self.certificates) * 3.0)
        cert_norm = (cert_score / 15.0) * 100.0 if cert_score else 0.0

        exp_score = min(15.0, len(self.experience) * 5.0)
        exp_norm = (exp_score / 15.0) * 100.0 if exp_score else 0.0

        awards_score = _infer_awards_score((self.awards or []) + (self.experience or []))
        research_score = _infer_research_score((self.research or []) + (self.experience or []))
        school_score = _infer_school_score((self.school_tier or "").strip())

        self.competitiveness_score = min(
            100.0,
            round(
                0.35 * soft_score
                + 0.25 * skill_score
                + 0.05 * cert_norm
                + 0.08 * exp_norm
                + 0.15 * awards_score
                + 0.10 * research_score
                + 0.02 * school_score,
                1,
            ),
        )

    def to_dimension_dict(self) -> dict[str, Any]:
        """转为四大维度结构，供匹配引擎使用"""
        return {
            "basic_requirements": {
                "certificates": self.certificates,
                "internship_experience": self.experience,
                "technical_depth": self.technical_depth,
            },
            "professional_skills": {
                "skills": self.skills,
                "technical_depth": self.technical_depth,
            },
            "professional_quality": {
                "communication": self.communication,
                "teamwork": self.teamwork,
                "stress_resistance": self.stress_resistance,
                "problem_solving": self.problem_solving,
            },
            "development_potential": {
                "learning_ability": self.learning_ability,
                "innovation_ability": self.innovation_ability,
            },
        }


class StudentProfileAnalyzer:
    """学生画像分析器（简历 / 表单 + LLM）"""

    def __init__(self, llm=None):
        self.llm = llm

    def analyze_from_resume(self, resume_file_path: str, mbti_type: str = "") -> "StudentProfile":
        """从简历文件解析并构建学生画像；mbti_type 为可选四字母类型（覆盖简历中推断）"""
        from services.resume_parser import parse_resume

        raw_text = parse_resume(resume_file_path)
        return self._build_profile_from_llm(
            raw_text,
            student_id=resume_file_path or "resume",
            mbti_override=mbti_type or "",
        )

    def analyze_from_form(self, form_data: dict) -> "StudentProfile":
        """从表单数据构建学生画像"""
        student_id = str(form_data.get("student_id", "anonymous"))
        profile = StudentProfile(student_id=student_id)
        default_skill_level = form_data.get("technical_depth", 3)
        skills = form_data.get("skills") or form_data.get("professional_skills")
        if isinstance(skills, dict):
            profile.skills = {k: int(v) if isinstance(v, (int, float)) else 3 for k, v in skills.items()}
        elif isinstance(skills, list):
            # 关键修复：若用户用“技能列表”方式填写，没有明确掌握等级，
            # 则技能默认掌握程度取自用户的 technical_depth 自评（避免“最低自评仍高分”）
            try:
                lvl = int(default_skill_level)
            except (ValueError, TypeError):
                lvl = 3
            lvl = max(1, min(5, lvl))
            profile.skills = {s: lvl for s in skills if s}
        profile.certificates = _ensure_list(form_data.get("certificates"))
        profile.experience = _ensure_list(form_data.get("experience")) or _ensure_list(form_data.get("internship_experience"))
        profile.awards = _ensure_list(form_data.get("awards_experience"))
        profile.research = _ensure_list(form_data.get("research_experience"))
        profile.career_preferences = form_data.get("career_preferences") or {}
        profile.school_tier = str(form_data.get("school_tier", "") or "").strip()
        if not profile.school_tier and isinstance(profile.career_preferences, dict):
            profile.school_tier = str(profile.career_preferences.get("school_tier", "") or "").strip()
        for key in ("innovation_ability", "learning_ability", "stress_resistance", "communication", "teamwork", "problem_solving", "technical_depth"):
            v = form_data.get(key)
            if v is not None:
                try:
                    setattr(profile, key, min(5, max(1, int(v))))
                except (ValueError, TypeError):
                    pass
        from models.mbti_mapping import apply_mbti_merge_to_profile, normalize_mbti

        prefs = form_data.get("career_preferences") if isinstance(form_data.get("career_preferences"), dict) else {}
        profile.mbti_type = normalize_mbti(
            form_data.get("mbti_type") or form_data.get("mbti") or prefs.get("mbti_type") or prefs.get("mbti")
        )
        apply_mbti_merge_to_profile(profile)
        profile.calculate_scores()
        return profile

    def _build_profile_from_llm(
        self,
        resume_text: str,
        student_id: str = "resume",
        mbti_override: str = "",
    ) -> "StudentProfile":
        """用 LLM 解析文本并填充 StudentProfile；可选用户指定的 MBTI 覆盖模型推断"""
        from models.mbti_mapping import apply_mbti_merge_to_profile, normalize_mbti

        profile = StudentProfile(student_id=student_id)
        data: dict = {}
        if self.llm and resume_text.strip():
            data = self.llm.analyze_student_profile(resume_text)
            if not isinstance(data, dict):
                data = {}
            ps = data.get("professional_skills")
            if isinstance(ps, dict):
                profile.skills = {k: _clip_level(v) for k, v in ps.items()}
            elif isinstance(ps, list):
                profile.skills = {s: 3 for s in ps if s}
            profile.certificates = _ensure_list(data.get("certificates"))
            exp = data.get("internship_experience") or data.get("experience")
            profile.experience = _ensure_list(exp)
            profile.awards = _ensure_list(data.get("awards_experience") or data.get("awards"))
            profile.research = _ensure_list(data.get("research_experience") or data.get("research"))
            profile.school_tier = str(data.get("school_tier", "") or "").strip()
            for key in ("innovation_ability", "learning_ability", "stress_resistance", "communication", "teamwork", "problem_solving", "technical_depth"):
                v = data.get(key)
                if v is not None:
                    profile.__setattr__(key, _clip_level(v))
        code = normalize_mbti(mbti_override)
        if not code:
            code = normalize_mbti((data or {}).get("mbti_type") or (data or {}).get("mbti"))
        profile.mbti_type = code or ""
        apply_mbti_merge_to_profile(profile)
        profile.calculate_scores()
        return profile

    def gap_analysis(self, student_profile: "StudentProfile", job_profile: Any) -> dict:
        """分析学生与目标岗位的能力差距"""
        missing_skills = []
        to_improve = {}
        advantage_skills = []
        job_skills = getattr(job_profile, "required_skills", []) or []
        job_certs = getattr(job_profile, "certificates", []) or []
        student_skills = student_profile.skills or {}
        student_certs = set(s.lower() for s in (student_profile.certificates or []))
        job_skill_set_lower = set()
        for s in job_skills:
            sk = s.strip().lower()
            if not sk:
                continue
            job_skill_set_lower.add(sk)
            level = student_skills.get(s) or student_skills.get(sk) or next((student_skills.get(k) for k in student_skills if sk in k.lower()), None)
            if level is None:
                missing_skills.append(s)
            elif level < 4:
                to_improve[s] = level
            else:
                advantage_skills.append(s)
        missing_certs = [c for c in job_certs if c and c.lower() not in student_certs]

        # 可迁移优势：掌握较好但未计入「相对优势技能」的技能（避免整块空白）
        core_strengths: list[str] = []
        if isinstance(student_skills, dict) and student_skills:
            ranked = sorted(student_skills.items(), key=lambda kv: (-int(kv[1]) if isinstance(kv[1], (int, float)) else 0, kv[0]))
            for name, lvl in ranked[:8]:
                if not isinstance(lvl, (int, float)) or lvl < 3:
                    continue
                nl = (name or "").strip().lower()
                if any(nl == j or nl in j or j in nl for j in job_skill_set_lower if j):
                    continue
                core_strengths.append(f"{name}（自评 {int(lvl)}/5，可写入经历与岗位建立关联）")
            if not core_strengths:
                for name, lvl in ranked[:5]:
                    if isinstance(lvl, (int, float)) and lvl >= 3:
                        core_strengths.append(f"{name}（自评 {int(lvl)}/5）")

        soft_dimension_hints: list[str] = []
        pairs = [
            ("沟通表达", "communication", getattr(job_profile, "communication", "")),
            ("团队协作", "teamwork", getattr(job_profile, "teamwork", "")),
            ("抗压与应变", "stress_resistance", getattr(job_profile, "stress_resistance", "")),
            ("问题解决", "problem_solving", getattr(job_profile, "problem_solving", "")),
        ]
        for label, attr, jtxt in pairs:
            sv = getattr(student_profile, attr, 0) or 0
            try:
                sv = int(sv)
            except (ValueError, TypeError):
                sv = 0
            jt = (jtxt or "").strip()
            if jt and 0 < sv <= 2:
                soft_dimension_hints.append(f"{label}：岗位相关描述较多，当前自评 {sv}/5，建议用具体事例佐证")
            elif jt and sv == 0 and ("沟通" in jt or "协作" in jt or "团队" in jt or "压力" in jt or "问题" in jt):
                soft_dimension_hints.append(f"{label}：建议在表单中补充自评，便于与岗位要求对照")

        if not (student_profile.experience or []) and (getattr(job_profile, "internship_experience", "") or "").strip():
            soft_dimension_hints.append("实习/项目：岗位强调实践经历，可补充课程设计、竞赛或实习描述")

        try:
            la = int(student_profile.learning_ability or 0)
        except (ValueError, TypeError):
            la = 0
        if (getattr(job_profile, "learning_ability", "") or "").strip() and la and la <= 2:
            soft_dimension_hints.append("学习能力：岗位关注持续学习，可适当提高自评并用学习成果举例")

        if (getattr(student_profile, "mbti_type", "") or "").strip():
            mt = str(student_profile.mbti_type).strip().upper()
            soft_dimension_hints.insert(
                0,
                f"MBTI 类型 {mt} 已与沟通、协作、抗压、问题解决、创新、学习六项自评融合；"
                "若自评与类型典型倾向冲突较大，以 MBTI 侧为优先参考。",
            )

        return {
            "missing_skills": missing_skills,
            "missing_certificates": missing_certs,
            "to_improve": to_improve,
            "advantage_skills": advantage_skills,
            "core_strengths": core_strengths[:6],
            "soft_dimension_hints": soft_dimension_hints[:8],
        }


def _ensure_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x]
    return [str(v).strip()]


def _clip_level(v: Any) -> int:
    try:
        x = int(v)
        return max(1, min(5, x))
    except (ValueError, TypeError):
        return 3


def _infer_awards_score(items: list[str]) -> float:
    """从奖项/竞赛文本推断含金量（0-100）"""
    if not items:
        return 0.0
    text = " ".join(items).lower()
    score = 0.0
    # 奖项级别
    if "国家" in text or "国奖" in text or "国际" in text:
        score += 60
    elif "省" in text or "部" in text:
        score += 40
    elif "市" in text or "厅" in text or "校" in text:
        score += 25
    # 获奖等级
    if any(k in text for k in ("一等奖", "特等奖")):
        score += 30
    elif "二等奖" in text:
        score += 20
    elif "三等奖" in text:
        score += 10
    # 竞赛关键词兜底
    if any(k in text for k in ("竞赛", "挑战赛", "大赛")):
        score += 10
    return min(100.0, score)


def _infer_research_score(items: list[str]) -> float:
    """从科研/论文/专利文本推断含金量（0-100）"""
    if not items:
        return 0.0
    text = " ".join(items).lower()
    score = 0.0
    # 论文/期刊
    if "sci" in text or "ei" in text:
        score += 55
    if "核心" in text or "期刊" in text:
        score += 25
    if "论文" in text:
        score += 15
    # 专利/项目
    if "发明专利" in text or "专利" in text:
        score += 25
    if "课题" in text or "科研" in text or "项目" in text:
        score += 15
    # 数量级适当加成
    score += min(20.0, len(items) * 5.0)
    return min(100.0, score)


def _infer_school_score(school_tier: str) -> float:
    """从院校层次字符串推断竞争力子分（0-100），与 add 版一致。"""
    if not school_tier:
        return 0.0
    tier = str(school_tier).lower()
    if "985" in tier:
        return 100.0
    if "211" in tier or "双一流" in tier:
        return 70.0
    if "普通" in tier or "一本" in tier or "二本" in tier:
        return 45.0
    if "专科" in tier or "高职" in tier:
        return 20.0
    return 30.0
