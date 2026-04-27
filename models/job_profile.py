# -*- coding: utf-8 -*-
"""岗位画像数据结构与构建器"""
from __future__ import annotations

from typing import Any, Optional

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
        # 尝试从职位描述中提取学历要求
        description = (self.description or "").lower()
        education = self.raw.get("学历要求", "")
        if not education:
            if "本科" in description:
                education = "本科及以上"
            elif "大专" in description:
                education = "大专及以上"
            elif "硕士" in description:
                education = "硕士及以上"
            elif "博士" in description:
                education = "博士及以上"
            else:
                education = "学历要求不限"
        
        return {
            "basic_requirements": {
                "education": education,
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


def is_computer_related_job(profile: Optional[JobProfile]) -> bool:
    """是否计算机 / IT 相关岗位（岗位图谱仅展示此类节点；基于行业 + 岗位名称/描述）。"""
    if profile is None:
        return False
    name = (profile.job_name or "").strip()
    desc = ((profile.description or "")[:900]).lower()
    name_l = name.lower()
    text = name_l + " " + desc

    exclude_title = (
        "销售总监",
        "销售经理",
        "商务总监",
        "人力资源",
        "行政专员",
        "出纳",
        "会计",
        "律师",
        "医生",
        "护士",
        "主播",
        "客服专员",
    )
    if any(b in name for b in exclude_title):
        return False

    tech_tokens = (
        "工程师",
        "开发",
        "程序员",
        "研发",
        "前端",
        "后端",
        "测试工程师",
        "软件测试",
        "运维",
        "算法",
        "架构",
        "java",
        "python",
        "c++",
        "c语言",
        "golang",
        "go语言",
        ".net",
        "安卓",
        "android",
        "ios",
        "鸿蒙",
        "大数据",
        "数据开发",
        "数据仓库",
        "dba",
        "数据库",
        "机器学习",
        "深度学习",
        "nlp",
        "cv",
        "嵌入式",
        "单片机",
        "fpga",
        "实施工程师",
        "系统工程师",
        "网络工程师",
        "安全工程师",
        "爬虫",
        "区块链",
        "php",
        "delphi",
        "rust",
        "kubernetes",
        "docker",
    )
    for k in tech_tokens:
        if k in text:
            return True

    ind = (profile.industry or "").strip()
    ind_l = ind.lower()
    ind_hits = (
        "计算机",
        "软件",
        "互联网",
        "人工智能",
        "信息安全",
        "云计算",
        "半导体",
        "集成电路",
        "网络游戏",
        "it服务",
        "it/",
        "通信",
        "电信",
        "电子技术",
    )
    if not any(k in ind_l or k in ind for k in ind_hits):
        return False
    role_hints = (
        "工程师",
        "开发",
        "程序",
        "技术",
        "运维",
        "测试",
        "算法",
        "架构",
        "研发",
        "数据",
        "产品",
        "前端",
        "后端",
        "设计",
    )
    return any(h in name for h in role_hints)


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
            if isinstance(extracted, dict):
                profile.required_skills = _ensure_list(extracted.get("professional_skills"))
                profile.certificates = _ensure_list(extracted.get("certificates"))
                profile.innovation_ability = _str_val(extracted.get("innovation_ability"))
                profile.learning_ability = _str_val(extracted.get("learning_ability"))
                profile.stress_resistance = _str_val(extracted.get("stress_resistance"))
                profile.communication = _str_val(extracted.get("communication"))
                profile.internship_experience = _str_val(extracted.get("internship_experience"))
                profile.teamwork = _str_val(extracted.get("teamwork"))
                profile.problem_solving = _str_val(extracted.get("problem_solving"))
                profile.technical_depth = _str_val(extracted.get("technical_depth"))
                for k, v in extracted.items():
                    if k not in (
                        "professional_skills", "certificates",
                        "innovation_ability", "learning_ability", "stress_resistance",
                        "communication", "internship_experience", "teamwork",
                        "problem_solving", "technical_depth",
                    ) and v:
                        profile.soft_skills[k] = v
        else:
            # 无 LLM 时从描述中做简单关键词填充，保证维度存在
            _fill_profile_from_description(profile)

        return profile

    def batch_build_profiles(self, job_data_list: list[dict]) -> dict[str, JobProfile]:
        """批量构建岗位画像字典 {job_id: JobProfile}。

        原始 CSV 中约数百条记录共享同一「职位编码」，若直接用作 dict 键会相互覆盖，
        导致近万条数据只建成九千余个画像。重复键时追加 __dupN 保证每条记录对应唯一画像。
        """
        result: dict[str, JobProfile] = {}
        for raw in job_data_list:
            profile = self.build_from_raw_data(raw)
            base_id = str(profile.job_id or "").strip() or "unknown"
            jid = base_id
            n = 0
            while jid in result:
                n += 1
                jid = f"{base_id}__dup{n}"
            if jid != base_id:
                profile.job_id = jid
            result[jid] = profile
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
    
    # 如果岗位描述为空，根据岗位名称生成描述
    if not profile.description:
        if "开发" in title or "工程师" in title:
            profile.description = f"{profile.job_name}主要负责软件系统的设计、开发、测试和维护工作。需要具备扎实的编程基础和相关技术栈，能够独立完成模块开发和问题解决。"
        elif "测试" in title:
            profile.description = f"{profile.job_name}主要负责软件产品的质量保证工作，包括测试用例设计、执行测试、缺陷跟踪和质量分析。需要熟悉测试流程和工具，确保产品质量。"
        elif "产品" in title:
            profile.description = f"{profile.job_name}主要负责产品的规划、设计和管理工作，包括需求分析、产品设计、用户体验优化和项目协调。需要具备产品思维和用户导向意识。"
        elif "运营" in title:
            profile.description = f"{profile.job_name}主要负责产品的运营推广工作，包括用户运营、内容运营、活动策划和数据分析。需要具备数据分析能力和用户增长思维。"
        elif "财务" in title or "会计" in title:
            profile.description = f"{profile.job_name}主要负责公司的财务管理和会计核算工作，包括账务处理、报表编制、税务申报和财务分析。需要具备财务专业知识和相关证书。"
        elif "销售" in title:
            profile.description = f"{profile.job_name}主要负责产品的销售和客户开发工作，包括客户拜访、需求沟通、商务谈判和客户关系维护。需要具备良好的沟通能力和销售技巧。"
        elif "人力" in title or "HR" in title:
            profile.description = f"{profile.job_name}主要负责公司的人力资源管理工作，包括招聘、培训、绩效考核、薪酬福利和员工关系管理。需要具备人力资源专业知识和沟通协调能力。"
        elif "设计" in title:
            profile.description = f"{profile.job_name}主要负责产品的视觉设计和用户界面设计工作，包括UI设计、交互设计和用户体验优化。需要具备设计软件操作能力和创意思维。"
        elif "数据分析" in title or "数据分析师" in title:
            profile.description = f"{profile.job_name}主要负责数据的收集、清洗、分析和可视化工作，为业务决策提供数据支持。需要具备数据分析技能和统计学知识。"
        elif "运维" in title:
            profile.description = f"{profile.job_name}主要负责系统的部署、监控、维护和优化工作，确保系统稳定运行。需要具备系统管理技能和故障排查能力。"
        elif "市场" in title or "营销" in title:
            profile.description = f"{profile.job_name}主要负责产品的市场推广和品牌建设工作，包括市场调研、营销策略制定和品牌传播。需要具备市场洞察能力和创意策划能力。"
        elif "客服" in title or "客户服务" in title:
            profile.description = f"{profile.job_name}主要负责客户的咨询解答、投诉处理和售后服务工作，提升客户满意度。需要具备良好的沟通能力和服务意识。"
        elif "行政" in title or "文秘" in title:
            profile.description = f"{profile.job_name}主要负责公司的行政管理和办公事务工作，包括文件处理、会议组织、接待安排和后勤保障。需要具备细致认真的工作态度和协调能力。"
        else:
            profile.description = f"{profile.job_name}主要负责相关业务领域的工作，需要具备该领域的专业知识和技能，以及良好的沟通协作能力。"

    # 1. 关键技能：更细粒度的关键词映射，增加更多技能和组合
    skill_map = {
        "c++": "C++",
        "c/c++": "C++",
        "cpp": "C++",
        "c语言": "C",
        " c ": "C",
        "c#": "C#",
        "python": "Python",
        "py3": "Python",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "java": "Java",
        "spring": "Spring",
        "spring boot": "Spring Boot",
        "mybatis": "MyBatis",
        "mysql": "MySQL",
        "oracle": "Oracle",
        "postgres": "PostgreSQL",
        "sql": "SQL",
        "redis": "Redis",
        "mongodb": "MongoDB",
        "kafka": "Kafka",
        "rabbitmq": "RabbitMQ",
        "spark": "Spark",
        "flink": "Flink",
        "hadoop": "Hadoop",
        "tensorflow": "TensorFlow",
        "pytorch": "PyTorch",
        "机器学习": "机器学习",
        "深度学习": "深度学习",
        "算法": "算法",
        "数据结构": "数据结构",
        "计算机网络": "计算机网络",
        "操作系统": "操作系统",
        "数据库原理": "数据库原理",
        "单元测试": "单元测试",
        "selenium": "Selenium",
        "接口测试": "接口测试",
        "jmeter": "JMeter",
        "测试": "测试",
        "vue": "Vue",
        "react": "React",
        "angular": "Angular",
        "前端": "前端开发",
        "后端": "后端开发",
        "html": "HTML",
        "css": "CSS",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "node.js": "Node.js",
        "docker": "Docker",
        "k8s": "Kubernetes",
        "kubernetes": "Kubernetes",
        "linux": "Linux",
        "运维": "运维",
        "ci/cd": "CI/CD",
        "git": "Git",
        "svn": "SVN",
        "figma": "Figma",
        "sketch": "Sketch",
        "ps": "Photoshop",
        "ai ": "Illustrator",
        "photoshop": "Photoshop",
        "作品集": "作品集",
        "产品": "产品管理",
        "运营": "运营",
        "数据分析": "数据分析",
        "数据挖掘": "数据挖掘",
        "统计学": "统计学",
        "excel": "Excel",
        "power bi": "Power BI",
        "tableau": "Tableau",
        "spss": "SPSS",
        "r语言": "R语言",
        "matlab": "MATLAB",
        "erp": "ERP",
        "财务": "财务",
        "会计": "会计",
        "审计": "审计",
        "金融": "金融",
        "市场营销": "市场营销",
        "销售": "销售",
        "人力资源": "人力资源",
        "行政": "行政",
        "文秘": "文秘",
        "法律": "法律",
        "法务": "法务",
    }
    for kw, skill in skill_map.items():
        if kw in text:
            if skill not in profile.required_skills:
                profile.required_skills.append(skill)

    # 根据岗位名称添加通用技能
    # 若岗位名称已明确语言方向，先补充语言主技能，避免“语言信息丢失”
    if "c++" in title or "c/c++" in title or "cpp" in title:
        if "C++" not in profile.required_skills:
            profile.required_skills.append("C++")
    if "java" in title and "Java" not in profile.required_skills:
        profile.required_skills.append("Java")
    if "python" in title and "Python" not in profile.required_skills:
        profile.required_skills.append("Python")

    # 细分轨道模板：避免所有“开发/工程师”都落入同一通用技能集合
    if any(k in title for k in ("前端", "web前端", "h5")):
        for s in ["JavaScript", "HTML", "CSS", "前端开发"]:
            if s not in profile.required_skills:
                profile.required_skills.append(s)
        if any(k in text for k in ("react", "vue", "typescript")):
            # 已在关键词中识别则保留，不额外重复
            pass
    elif any(k in title for k in ("后端", "服务端")):
        for s in ["后端开发", "SQL", "接口设计"]:
            if s not in profile.required_skills:
                profile.required_skills.append(s)
    elif any(k in title for k in ("数据库", "dba", "数据管理")):
        for s in ["SQL", "数据库原理", "数据库性能优化"]:
            if s not in profile.required_skills:
                profile.required_skills.append(s)
    elif any(k in title for k in ("数据开发", "数据工程", "数仓", "etl")):
        for s in ["SQL", "ETL", "数据建模"]:
            if s not in profile.required_skills:
                profile.required_skills.append(s)
    elif any(k in title for k in ("科研", "研究员", "算法研究")):
        for s in ["算法", "论文阅读", "实验设计"]:
            if s not in profile.required_skills:
                profile.required_skills.append(s)
    elif "开发" in title or "工程师" in title:
        if "Python" not in profile.required_skills:
            profile.required_skills.append("编程基础")
        if "数据结构" not in profile.required_skills:
            profile.required_skills.append("数据结构")
        if "算法" not in profile.required_skills:
            profile.required_skills.append("算法")
    elif "测试" in title:
        if "测试" not in profile.required_skills:
            profile.required_skills.append("软件测试")
        profile.required_skills.append("测试用例设计")
    elif "产品" in title:
        profile.required_skills.append("产品思维")
        profile.required_skills.append("用户体验设计")
    elif "运营" in title:
        profile.required_skills.append("数据分析")
        profile.required_skills.append("用户运营")
    elif "财务" in title or "会计" in title:
        profile.required_skills.append("财务分析")
        profile.required_skills.append("会计核算")
    elif "销售" in title:
        profile.required_skills.append("销售技巧")
        profile.required_skills.append("客户管理")
    elif "人力" in title or "HR" in title:
        profile.required_skills.append("人力资源管理")
        profile.required_skills.append("招聘")

    # fallback：如果一个技能都没识别到，根据岗位类型添加相关技能
    if not profile.required_skills and text:
        if "开发" in title or "工程师" in title:
            profile.required_skills = ["编程基础", "数据结构", "算法", "计算机基础"]
        elif "测试" in title:
            profile.required_skills = ["软件测试", "测试用例设计", "缺陷管理"]
        elif "产品" in title:
            profile.required_skills = ["产品思维", "用户体验", "需求分析"]
        elif "运营" in title:
            profile.required_skills = ["数据分析", "用户运营", "内容运营"]
        else:
            profile.required_skills = ["通用办公能力", "沟通协作"]

    # 2. 证书要求：基于文本中出现的典型词，并根据岗位类型推荐
    cert_map = [
        ("英语四级", "英语四级"),
        ("cet-4", "英语四级"),
        ("英语六级", "英语六级"),
        ("cet-6", "英语六级"),
        ("软考", "软考"),
        ("信息系统项目管理师", "软考-信息系统项目管理师"),
        ("系统架构师", "软考-系统架构师"),
        ("软件设计师", "软考-软件设计师"),
        ("计算机二级", "计算机二级"),
        ("计算机三级", "计算机三级"),
        ("计算机四级", "计算机四级"),
        ("驾照", "驾照"),
        ("托福", "托福"),
        ("雅思", "雅思"),
        ("cpa", "注册会计师"),
        ("acca", "ACCA"),
        ("cma", "管理会计"),
        ("frm", "金融风险管理师"),
        ("cfa", "特许金融分析师"),
        ("教师资格证", "教师资格证"),
    ]
    for kw, cert in cert_map:
        if kw.lower() in text:
            if cert not in profile.certificates:
                profile.certificates.append(cert)

    # 根据岗位类型推荐证书
    if "财务" in title or "会计" in title:
        if "注册会计师" not in profile.certificates:
            profile.certificates.append("注册会计师")
        profile.certificates.append("初级会计职称")
    elif "金融" in title:
        profile.certificates.append("金融从业资格证")
        profile.certificates.append("证券从业资格证")
    elif "教育" in title or "教师" in title:
        profile.certificates.append("教师资格证")
    elif "开发" in title or "工程师" in title:
        profile.certificates.append("计算机二级")
        profile.certificates.append("英语四级")

    # 3. 实习/项目经验要求
    if any(k in text for k in ("实习", "项目经验", "有相关经验", "相关项目", "参与项目", "工作经验", "经验")):
        profile.internship_experience = "具备相关领域实习或项目经验，有完整项目经历者优先"
    else:
        # 根据岗位类型添加经验要求
        if "开发" in title or "工程师" in title:
            profile.internship_experience = "具备软件开发实习经验，参与过完整项目开发周期"
        elif "测试" in title:
            profile.internship_experience = "具备软件测试实习经验，熟悉测试流程和工具"
        elif "产品" in title:
            profile.internship_experience = "具备产品经理实习经验，参与过产品规划和设计"
        elif "运营" in title:
            profile.internship_experience = "具备互联网运营实习经验，熟悉用户运营和内容运营"
        else:
            profile.internship_experience = "具备相关领域实习经验优先"

    # 4. 技术深度/基础：当出现技术/框架词时认为岗位强调技术深度
    if any(k in text for k in ("架构", "性能", "优化", "高并发", "分布式", "深度学习", "模型", "系统设计", "研发", "技术", "算法", "数据结构")):
        profile.technical_depth = "岗位强调技术深度与工程实践能力，需要扎实的专业基础"
    else:
        # 根据岗位类型添加技术深度要求
        if "开发" in title or "工程师" in title:
            profile.technical_depth = "需要扎实的编程基础和技术功底，熟悉相关技术栈"
        elif "测试" in title:
            profile.technical_depth = "需要了解软件开发流程和测试方法论，具备一定的技术理解能力"
        elif "产品" in title:
            profile.technical_depth = "需要理解技术可行性，能够与技术团队有效沟通"
        else:
            profile.technical_depth = "具备岗位所需的专业基础知识和技能"

    # 5. 软素养/潜力字段：根据出现的描述决定是否“岗位明确提出”
    if any(k in text for k in ("沟通", "表达", "汇报", "协调", "交流", "沟通能力")):
        profile.communication = "岗位重视沟通与表达能力，能够清晰表达想法和观点"
    else:
        profile.communication = "具备良好的沟通表达能力，能够与团队成员有效沟通"

    if any(k in text for k in ("团队", "协作", "共同", "合作", "团队协作")):
        profile.teamwork = "岗位重视团队协作能力，能够融入团队并发挥协作精神"
    else:
        profile.teamwork = "具备良好的团队协作精神，能够与团队成员密切配合"

    if any(k in text for k in ("抗压", "压力", "承压", "高压", "节奏", "deadline", "高强度")):
        profile.stress_resistance = "岗位重视抗压能力，能够承受工作压力和挑战"
    else:
        profile.stress_resistance = "具备一定的抗压能力，能够应对工作中的压力和挑战"

    if any(k in text for k in ("解决问题", "问题解决", "排障", "定位", "故障分析", "问题分析")):
        profile.problem_solving = "岗位重视问题解决能力，能够独立分析和解决工作中的问题"
    else:
        profile.problem_solving = "具备良好的问题分析和解决能力，能够应对工作中的各种问题"

    if any(k in text for k in ("创新", "创新能力", "竞赛", "科研", "论文", "专利", "研发", "创意")):
        profile.innovation_ability = "岗位重视创新能力，能够提出创新性的解决方案和想法"
    else:
        profile.innovation_ability = "具备创新思维，能够提出改进建议和创新想法"

    if any(k in text for k in ("学习能力", "快速学习", "自驱", "自学能力", "成长", "成长性", "持续学习")):
        profile.learning_ability = "岗位重视学习能力与成长性，具备持续学习和自我提升的能力"
    else:
        profile.learning_ability = "具备良好的学习能力，能够快速掌握新知识和技能"
