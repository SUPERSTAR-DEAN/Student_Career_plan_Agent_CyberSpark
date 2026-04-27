# -*- coding: utf-8 -*-
"""学生就业能力画像与分析器"""
from __future__ import annotations

from typing import Any, Optional
from config import AppConfig  # 现在正常导入！


def _norm_score(v: Any) -> float:   #没有用到
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
        self.student_id: str = student_id or "anonymous"
        
        # 技能、证书、经历（列表/字典）
        self.skills: dict[str, int] = {}
        self.certificates: list[str] = []
        self.experience: list[str] = []
        self.awards: list[str] = []
        self.research: list[str] = []
        
        # 学校层次（字符串）
        self.school_tier: str = ""
        
        # 职业偏好（字典）
        self.career_preferences: dict[str, Any] = {}
        
        # 评分
        self.competitiveness_score: float = 0.0
        self.completeness_score: float = 0.0
        
        # 7项软实力
        self.innovation_ability: int = 0
        self.learning_ability: int = 0
        self.stress_resistance: int = 0
        self.communication: int = 0
        self.teamwork: int = 0
        self.problem_solving: int = 0
        self.technical_depth: int = 0

    def calculate_scores(self) -> None:
        """计算竞争力与完整度评分（权威权重版）"""
        # ==========================
        # 一、信息完整度计算（全覆盖所有字段）
        # ==========================
        completeness = 0.0

        # 1. 技能 (10分)
        if self.skills:
            completeness += 10

        # 2. 证书 (10分)
        if self.certificates:
            completeness += 10

        # 3. 实习/项目 (10分)
        if self.experience:
            completeness += 10

        # 4. 奖项 (10分)
        if self.awards:
            completeness += 10

        # 5. 科研/论文 (10分)
        if self.research:
            completeness += 10

        # 6. 学校层次 (5分)
        if self.school_tier:
            completeness += 5

        # 7. 职业偏好 (10分)
        if self.career_preferences:
            completeness += 10

        # 8. 7项软实力维度 (35分)
        dims = [
            self.innovation_ability, self.learning_ability, self.stress_resistance,
            self.communication, self.teamwork, self.problem_solving, self.technical_depth,
        ]
        filled = sum(1 for d in dims if d and d > 0)
        completeness += 5 * filled

        # 最终完整度（不超过100）
        self.completeness_score = min(100.0, round(completeness, 1))

        # ==========================
        # 二、竞争力评分（权威权重）
        # ==========================
        # 1) 软实力（沟通、团队、学习等）
        soft_score = sum(_level_to_score(d) for d in dims) / 7 if dims else 0.0

        # 2) 专业技能得分
        if self.skills:
            avg_skill_level = sum(self.skills.values()) / len(self.skills)
            skill_score = (avg_skill_level - 1) / 4.0 * 100.0
        else:
            skill_score = 0.0

        # 3) 证书得分
        cert_score = min(15.0, len(self.certificates) * 3.0)
        cert_norm = (cert_score / 15.0) * 100.0 if cert_score else 0.0

        # 4) 实习/项目得分
        exp_score = min(15.0, len(self.experience) * 5.0)
        exp_norm = (exp_score / 15.0) * 100.0 if exp_score else 0.0

        # 5) 奖项含金量
        awards_score = _infer_awards_score((self.awards or []) + (self.experience or []))

        # 6) 科研含金量
        research_score = _infer_research_score((self.research or []) + (self.experience or []))

        # 7) 院校层次（从独立字段 school_tier 获取）
        school_score = _infer_school_score(self.school_tier)

        # ==========================
        # 加权总分（权威权重，总和1.0）
        # ==========================
        self.competitiveness_score = min(
            100.0,
            0.35 * soft_score    # 软实力：35%（职场核心）
            + 0.25 * skill_score # 专业技能：25%（硬门槛）
            + 0.05 * cert_norm   # 证书：5%（准入加分）
            + 0.08 * exp_norm    # 实习/项目：8%（上手能力）
            + 0.15 * awards_score# 奖项：15%（优秀区分）
            + 0.10 * research_score # 科研：10%（研发/学术潜力）
            + 0.02 * school_score# 学校：2%（背景门槛，权重低）
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

    def analyze_from_resume(self, resume_file_path: str) -> "StudentProfile":
        """从简历文件解析并构建学生画像"""
        from services.resume_parser import parse_resume
        raw_text = parse_resume(resume_file_path)
        return self._build_profile_from_llm(raw_text, student_id=resume_file_path or "resume")

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
        profile.school_tier = str(form_data.get("school_tier", ""))
        for key in ("innovation_ability", "learning_ability", "stress_resistance", "communication", "teamwork", "problem_solving", "technical_depth"):
            v = form_data.get(key)
            if v is not None:
                try:
                    setattr(profile, key, min(5, max(1, int(v))))
                except (ValueError, TypeError):
                    pass
        profile.calculate_scores()
        return profile

    def _build_profile_from_llm(self, resume_text: str, student_id: str = "resume") -> "StudentProfile":
        """用 LLM 解析文本并填充 StudentProfile"""
        profile = StudentProfile(student_id=student_id)
        if self.llm and resume_text.strip():
            data = self.llm.analyze_student_profile(resume_text)
            if isinstance(data, dict):
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
                for key in ("innovation_ability", "learning_ability", "stress_resistance", "communication", "teamwork", "problem_solving", "technical_depth"):
                    v = data.get(key)
                    if v is not None:
                        profile.__setattr__(key, _clip_level(v))
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
        for s in job_skills:
            sk = s.strip().lower()
            if not sk:
                continue
            level = student_skills.get(s) or student_skills.get(sk) or next((student_skills.get(k) for k in student_skills if sk in k.lower()), None)
            if level is None:
                missing_skills.append(s)
            elif level < 4:
                to_improve[s] = level
            else:
                advantage_skills.append(s)
        missing_certs = [c for c in job_certs if c and c.lower() not in student_certs]
        return {
            "missing_skills": missing_skills,
            "missing_certificates": missing_certs,
            "to_improve": to_improve,
            "advantage_skills": advantage_skills,
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
    """从学校层次推断分数（0-100）"""
    if not school_tier:
        return 0.0
    tier = str(school_tier).lower()
    if "985" in tier:
        return 100.0
    if "211" in tier or "双一流" in tier:
        return 70.0
    if "普通" in tier or "一本" in tier:
        return 45.0
    if "专科" in tier:
        return 20.0
    return 30.0

# ======================
# 测试代码：直接运行看效果
# ======================
if __name__ == '__main__':
    # 构造一个模拟学生表单数据（所有字段齐全）
    test_form_data = {
        "student_id": "TEST001",
        "skills": ["Python", "Java", "SQL", "Vue"],
        "technical_depth": 3,
        "certificates": ["计算机二级", "英语四级"],
        "experience": ["某公司后端开发实习", "校园管理系统项目"],
        "awards_experience": ["校级三等奖学金"],
        "research_experience": ["校级机器学习课题"],
        "school_tier": "普通本科",
        "career_preferences": {
            "intended_position": "后端开发工程师",
            "expected_city": "一线城市",
            "salary_expectation": 8000
        },
        "innovation_ability": 4,
        "learning_ability": 4,
        "stress_resistance": 3,
        "communication": 4,
        "teamwork": 3,
        "problem_solving": 3
    }

    # 1. 构建学生画像
    analyzer = StudentProfileAnalyzer()
    student = analyzer.analyze_from_form(test_form_data)

    # 2. 输出画像信息
    print("=" * 50)
    print("【学生基本信息】")
    print(f"学生ID：{student.student_id}")
    print(f"竞争力得分：{student.competitiveness_score:.1f}")
    print(f"信息完整度：{student.completeness_score:.1f}")
    print("=" * 50)

    print("\n【学生技能】")
    for k, v in student.skills.items():
        print(f"- {k}: {v}级")

    print("\n【证书】")
    for c in student.certificates:
        print(f"- {c}")

    print("\n【实习/项目】")
    for e in student.experience:
        print(f"- {e}")

    print("\n【奖项】")
    for a in student.awards:
        print(f"- {a}")

    print("\n【科研/论文】")
    for r in student.research:
        print(f"- {r}")

    print("\n【学校层次】")
    print(student.school_tier)

    print("\n【岗位偏好】")
    print(student.career_preferences)

    print("\n【软实力评分 1~5】")
    print(f"创新能力：{student.innovation_ability}")
    print(f"学习能力：{student.learning_ability}")
    print(f"抗压能力：{student.stress_resistance}")
    print(f"沟通能力：{student.communication}")
    print(f"团队合作：{student.teamwork}")
    print(f"问题解决：{student.problem_solving}")
    print(f"技术深度：{student.technical_depth}")
    print("=" * 50)

    # 3. 输出维度字典（给AI匹配用的数据）
    print("\n【输出给匹配系统的维度数据】")
    dim = student.to_dimension_dict()
    import json
    print(json.dumps(dim, ensure_ascii=False, indent=2))

    # 4. 测试差距分析（造一个模拟岗位）
    class MockJob:
        def __init__(self):
            self.required_skills = ["Python", "SQL", "Redis", "Docker"]
            self.certificates = ["计算机二级"]

    job = MockJob()
    gap = analyzer.gap_analysis(student, job)

    print("\n\n【🚀 岗位差距分析结果】")
    print("缺失技能：", gap["missing_skills"])
    print("缺失证书：", gap["missing_certificates"])
    print("需要提升：", gap["to_improve"])
    print("优势技能：", gap["advantage_skills"])