# -*- coding: utf-8 -*-
"""应用全局配置"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent


class AppConfig:
    """应用全局配置"""

    # 大模型配置（默认使用千问，可通过环境变量覆盖）
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    # 千问 DashScope OpenAI 兼容接口
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen-max")

    # 路径配置
    DATA_DIR = PROJECT_ROOT / "data"
    JOB_DATA_PATH = DATA_DIR / "raw" / "job_data.csv"
    GRAPH_OUTPUT_PATH = DATA_DIR / "graphs" / "career_graph.gml"
    GRAPH_JSON_PATH = DATA_DIR / "graphs" / "career_graph.json"
    MATCH_TEST_CASES_PATH = DATA_DIR / "test" / "match_test_cases.json"

    # 人岗匹配六大维度权重（职业素养、发展潜力各拆为两项，权重和为 1）
    MATCH_WEIGHTS = {
        "basic_requirements": 0.25,
        "professional_skills": 0.35,
        "communication_teamwork": 0.125,
        "stress_problem_solving": 0.125,
        "learning_ability": 0.075,
        "innovation_ability": 0.075,
    }

    # 岗位画像维度（不少于10个）
    JOB_PROFILE_DIMENSIONS = [
        "professional_skills",   # 专业技能
        "certificates",          # 证书要求
        "innovation_ability",    # 创新能力
        "learning_ability",      # 学习能力
        "stress_resistance",     # 抗压能力
        "communication",        # 沟通能力
        "internship_experience", # 实习/项目经验
        "teamwork",             # 团队协作
        "problem_solving",      # 问题解决能力
        "technical_depth",      # 技术深度
    ]

    # 学生画像与岗位画像对齐的维度
    STUDENT_PROFILE_DIMENSIONS = [
        "professional_skills",
        "certificates",
        "innovation_ability",
        "learning_ability",
        "stress_resistance",
        "communication",
        "internship_experience",
        "teamwork",
        "problem_solving",
        "technical_depth",
    ]

    @classmethod
    def ensure_dirs(cls) -> None:
        """确保数据目录存在"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "raw").mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "graphs").mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "test").mkdir(parents=True, exist_ok=True)
