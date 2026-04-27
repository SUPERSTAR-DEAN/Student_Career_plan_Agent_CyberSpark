# -*- coding: utf-8 -*-
"""岗位画像数据结构与构建器"""
from __future__ import annotations

from typing import Any, Optional

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))  # 把项目根目录加入路径
from config import AppConfig


class JobProfile:
    """单个岗位画像数据结构（含不少于10个维度）"""

    def __init__(self, job_id: str, job_name: str, raw: Optional[dict] = None):
        self.job_id = job_id
        self.job_name = job_name
        self.raw = raw or {}
        # 专业技能列表
        self.required_skills: list[str] = []
        # 证书要求
        self.certificates: list[str] = []
        # 软技能/素养：能力名 -> 要求描述或等级
        self.soft_skills: dict[str, Any] = {}
        # 晋升路径 {下一岗位名: 描述或权重}
        self.career_path: dict[str, Any] = {}
        # 换岗路径：相关岗位 id 或名称列表
        self.related_jobs: list[str] = []
        # 扩展维度：与 AppConfig.JOB_PROFILE_DIMENSIONS 对齐
        self.innovation_ability: str = ""
        self.learning_ability: str = ""
        self.stress_resistance: str = ""
        self.communication: str = ""
        self.internship_experience: str = ""
        self.teamwork: str = ""
        self.problem_solving: str = ""
        self.technical_depth: str = ""
        # 岗位描述、行业、薪资等
        self.description: str = ""
        self.industry: str = ""
        self.salary_range: str = ""
        self.location: str = ""
        self.company_name: str = ""

    def to_dimension_dict(self) -> dict[str, Any]:
        """提取为四大维度（基础要求、专业技能、职业素养、发展潜力）及细粒度维度，供匹配使用"""
        return {
            "basic_requirements": {
                "education": self.raw.get("学历要求", ""),
                "certificates": self.certificates,
                "internship_experience": self.internship_experience,
                "technical_depth": self.technical_depth,
            },
            "professional_skills": {
                "skills": self.required_skills,
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
            # 细粒度（用于关键技能匹配准确率）
            "professional_skills_list": self.required_skills,
            "certificates_list": self.certificates,
        }

    def extract_key_dimensions(self) -> dict[str, Any]:
        """提取岗位四大维度摘要，与 to_dimension_dict 一致，别名兼容"""
        return self.to_dimension_dict()


class JobProfileBuilder:
    """岗位画像构建器（支持从原始数据 + LLM 提取）"""

    def __init__(self, llm=None):
        self.llm = llm

    def build_from_raw_data(self, raw_job_data: dict) -> JobProfile:
        """从单条原始岗位数据构建结构化岗位画像"""
        job_id = str(
            raw_job_data.get("职位编码")
            or raw_job_data.get("job_code")
            or f"{raw_job_data.get('职位名称', '')}_{raw_job_data.get('公司全称', '')}"[:80]
        ).strip() or "unknown"
        job_name = (
            raw_job_data.get("职位名称") or raw_job_data.get("job_title") or "未知岗位"
        ).strip()
        profile = JobProfile(job_id=job_id, job_name=job_name, raw=dict(raw_job_data))
        profile.description = (
            raw_job_data.get("职位描述") or raw_job_data.get("job_description") or ""
        )
        profile.industry = raw_job_data.get("所属行业") or raw_job_data.get("industry") or ""
        profile.salary_range = raw_job_data.get("薪资范围") or raw_job_data.get("salary") or ""
        profile.location = raw_job_data.get("工作地址") or raw_job_data.get("location") or ""
        profile.company_name = raw_job_data.get("公司全称") or raw_job_data.get("company_name") or ""

        if self.llm and profile.description:
            extracted = self.llm.extract_job_requirements(profile.description)
            # 技能
            profile.required_skills = _ensure_list(extracted.get("professional_skills", []))
            # 证书
            profile.certificates = _ensure_list(extracted.get("certificates", []))
            # 软实力
            profile.innovation_ability = _str_val(extracted.get("innovation_ability"))
            profile.learning_ability = _str_val(extracted.get("learning_ability"))
            profile.stress_resistance = _str_val(extracted.get("stress_resistance"))
            profile.communication = _str_val(extracted.get("communication"))
            profile.internship_experience = _str_val(extracted.get("internship_experience"))
            profile.teamwork = _str_val(extracted.get("teamwork"))
            profile.problem_solving = _str_val(extracted.get("problem_solving"))
            profile.technical_depth = _str_val(extracted.get("technical_depth"))
        else:
            # 无 LLM 时从描述中做简单关键词填充，保证维度存在
            _fill_profile_from_description(profile)

        return profile

    def batch_build_profiles(self, job_data_list: list[dict]) -> dict[str, JobProfile]:
        """批量构建岗位画像字典 {job_id: JobProfile}"""
        result = {}
        for raw in job_data_list:
            profile = self.build_from_raw_data(raw)
            result[profile.job_id] = profile
        return result

    def extract_key_dimensions(self, job_profile: JobProfile) -> dict:
        """提取岗位四大维度（兼容旧接口）"""
        return job_profile.extract_key_dimensions()


def _ensure_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x]
    return [str(v).strip()]


def _str_val(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _fill_profile_from_description(profile: JobProfile) -> None:
    """无 LLM 时根据职位描述做关键词填充（提升岗位差异性）

    目标：
    1）让岗位的 4 大维度（基础/技能/素养/潜力）都有“可被岗位差异影响”的信息；
    2）避免所有岗位因为“soft 字段为空或统一”导致匹配结果趋同。
    """
    d = (profile.description or "").lower()
    title = (profile.job_name or "").lower()
    text = f"{title}\n{d}"

    # 1. 关键技能：更细粒度的关键词映射
    skill_map = {
        "python": "Python",
        "py3": "Python",
        "django": "Django",
        "flask": "Flask",
        "java": "Java",
        "spring": "Spring",
        "spring boot": "Spring Boot",
        "mysql": "MySQL",
        "oracle": "Oracle",
        "postgres": "PostgreSQL",
        "sql": "SQL",
        "redis": "Redis",
        "kafka": "Kafka",
        "spark": "Spark",
        "flink": "Flink",
        "tensorflow": "TensorFlow",
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "机器学习": "机器学习",
        "深度学习": "深度学习",
        "算法": "算法",
        "数据结构": "数据结构",
        "单元测试": "单元测试",
        "selenium": "Selenium",
        "接口测试": "接口测试",
        "jmeter": "JMeter",
        "测试": "测试",
        "vue": "Vue",
        "react": "React",
        "前端": "前端开发",
        "后端": "后端开发",
        "html": "HTML",
        "css": "CSS",
        "javascript": "JavaScript",
        "node.js": "Node.js",
        "docker": "Docker",
        "k8s": "Kubernetes",
        "kubernetes": "Kubernetes",
        "linux": "Linux",
        "运维": "运维",
        "figma": "Figma",
        "sketch": "Sketch",
        "ps": "Photoshop",
        "ai ": "Illustrator",
        "photoshop": "Photoshop",
        "作品集": "作品集",
    }
    for kw, skill in skill_map.items():
        if kw in text:
            if skill not in profile.required_skills:
                profile.required_skills.append(skill)

    # fallback：如果一个技能都没识别到，仍放一个中性技能，避免 professional_skills 维度全为空导致统一中性
    if not profile.required_skills and text:
        profile.required_skills = ["通用开发能力"]

    # 2. 证书要求：基于文本中出现的典型词
    cert_map = [
        ("英语四级", "英语四级"),
        ("cet-4", "英语四级"),
        ("英语六级", "英语六级"),
        ("cet-6", "英语六级"),
        ("软考", "软考"),
        ("信息系统项目管理师", "软考-信息系统项目管理师"),
        ("计算机二级", "计算机二级"),
        ("驾照", "驾照"),
        ("托福", "托福"),
        ("雅思", "雅思"),
    ]
    for kw, cert in cert_map:
        if kw.lower() in text:
            if cert not in profile.certificates:
                profile.certificates.append(cert)

    # 3. 实习/项目经验要求
    if any(k in text for k in ("实习", "项目经验", "有相关经验", "相关项目", "参与项目")):
        profile.internship_experience = "具备实习或项目经验优先"

    # 4. 技术深度/基础：当出现技术/框架词时认为岗位强调技术深度
    if any(k in text for k in ("架构", "性能", "优化", "高并发", "分布式", "深度学习", "模型", "系统设计", "研发", "技术")):
        profile.technical_depth = "岗位强调技术深度与工程实践"

    # 5. 软素养/潜力字段：根据出现的描述决定是否“岗位明确提出”
    if any(k in text for k in ("沟通", "表达", "汇报", "协调")):
        profile.communication = "岗位重视沟通与表达能力"
    if any(k in text for k in ("团队", "协作", "共同", "合作")):
        profile.teamwork = "岗位重视团队协作能力"
    if any(k in text for k in ("抗压", "压力", "承压", "高压", "节奏", "deadline")):
        profile.stress_resistance = "岗位重视抗压能力"
    if any(k in text for k in ("解决问题", "问题解决", "排障", "定位", "故障分析")):
        profile.problem_solving = "岗位重视问题解决能力"

    if any(k in text for k in ("创新", "创新能力", "竞赛", "科研", "论文", "专利", "研发")):
        profile.innovation_ability = "岗位重视创新能力"
    if any(k in text for k in ("学习能力", "快速学习", "自驱", "自学能力", "成长", "成长性")):
        profile.learning_ability = "岗位重视学习能力与成长性"

    # 若仍为空，则保持为空（让匹配引擎返回中性分50），避免所有岗位都被同一种默认值填满造成趋同