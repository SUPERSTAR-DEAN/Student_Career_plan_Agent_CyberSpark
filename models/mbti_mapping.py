# -*- coding: utf-8 -*-
"""MBTI 与能力自评融合：类型校验、典型维度分表、冲突时优先 MBTI。"""
from __future__ import annotations

from typing import Any

# 16 型；每项为 1–5：沟通、协作、抗压、问题解决、创新、学习（技术深度不参与 MBTI 校正）
MBTI_ABILITY_SCORES: dict[str, dict[str, int]] = {
    "INTJ": {"communication": 3, "teamwork": 3, "stress_resistance": 4, "problem_solving": 5, "innovation_ability": 5, "learning_ability": 5},
    "INTP": {"communication": 3, "teamwork": 3, "stress_resistance": 3, "problem_solving": 5, "innovation_ability": 5, "learning_ability": 5},
    "ENTJ": {"communication": 5, "teamwork": 4, "stress_resistance": 5, "problem_solving": 5, "innovation_ability": 4, "learning_ability": 4},
    "ENTP": {"communication": 5, "teamwork": 4, "stress_resistance": 4, "problem_solving": 4, "innovation_ability": 5, "learning_ability": 5},
    "INFJ": {"communication": 4, "teamwork": 4, "stress_resistance": 3, "problem_solving": 4, "innovation_ability": 4, "learning_ability": 4},
    "INFP": {"communication": 3, "teamwork": 4, "stress_resistance": 3, "problem_solving": 3, "innovation_ability": 4, "learning_ability": 4},
    "ENFJ": {"communication": 5, "teamwork": 5, "stress_resistance": 4, "problem_solving": 3, "innovation_ability": 4, "learning_ability": 4},
    "ENFP": {"communication": 5, "teamwork": 5, "stress_resistance": 3, "problem_solving": 3, "innovation_ability": 5, "learning_ability": 4},
    "ISTJ": {"communication": 3, "teamwork": 4, "stress_resistance": 4, "problem_solving": 4, "innovation_ability": 2, "learning_ability": 3},
    "ISFJ": {"communication": 4, "teamwork": 4, "stress_resistance": 4, "problem_solving": 3, "innovation_ability": 2, "learning_ability": 3},
    "ESTJ": {"communication": 4, "teamwork": 4, "stress_resistance": 5, "problem_solving": 4, "innovation_ability": 2, "learning_ability": 3},
    "ESFJ": {"communication": 5, "teamwork": 5, "stress_resistance": 4, "problem_solving": 3, "innovation_ability": 2, "learning_ability": 3},
    "ISTP": {"communication": 3, "teamwork": 3, "stress_resistance": 4, "problem_solving": 4, "innovation_ability": 3, "learning_ability": 3},
    "ISFP": {"communication": 3, "teamwork": 4, "stress_resistance": 3, "problem_solving": 3, "innovation_ability": 3, "learning_ability": 3},
    "ESTP": {"communication": 5, "teamwork": 4, "stress_resistance": 4, "problem_solving": 4, "innovation_ability": 3, "learning_ability": 3},
    "ESFP": {"communication": 5, "teamwork": 5, "stress_resistance": 3, "problem_solving": 3, "innovation_ability": 3, "learning_ability": 3},
}

MBTI_SOFT_DIMS: tuple[str, ...] = (
    "communication",
    "teamwork",
    "stress_resistance",
    "problem_solving",
    "innovation_ability",
    "learning_ability",
)

VALID_MBTI_TYPES = frozenset(MBTI_ABILITY_SCORES.keys())


def normalize_mbti(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().upper().replace(" ", "").replace("-", "")
    if len(s) == 4 and s in VALID_MBTI_TYPES:
        return s
    return ""


def _merge_one_dimension(self_rating: int, mbti_rating: int) -> int:
    """
    自评与 MBTI 典型分融合。无自评(0)时采用 MBTI；有自评时：
    差值≥2 视为冲突 → 以 MBTI 为准；差值=1 → 明显倾向 MBTI；一致或接近 → 略倾向 MBTI 加权。
    """
    m = max(1, min(5, int(mbti_rating)))
    if self_rating is None or int(self_rating) <= 0:
        return m
    s = max(1, min(5, int(self_rating)))
    diff = abs(s - m)
    if diff >= 2:
        return m
    if diff == 1:
        return max(1, min(5, int(round(0.22 * s + 0.78 * m))))
    return max(1, min(5, int(round(0.42 * s + 0.58 * m))))


def apply_mbti_merge_to_profile(profile: Any) -> None:
    """根据 profile.mbti_type 校正六项软实力（不改 technical_depth）。"""
    code = normalize_mbti(getattr(profile, "mbti_type", "") or "")
    if not code:
        setattr(profile, "mbti_type", "")
        return
    setattr(profile, "mbti_type", code)
    table = MBTI_ABILITY_SCORES.get(code)
    if not table:
        return
    for dim in MBTI_SOFT_DIMS:
        self_v = getattr(profile, dim, 0) or 0
        try:
            self_v = int(self_v)
        except (ValueError, TypeError):
            self_v = 0
        mbti_v = int(table.get(dim, 3))
        merged = _merge_one_dimension(self_v, mbti_v)
        setattr(profile, dim, merged)


def get_mbti_label_zh(code: str) -> str:
    """简要中文类型说明（用于报告展示）。"""
    c = normalize_mbti(code)
    if not c:
        return ""
    # 仅作轻量展示，非完整类型描述
    parts = []
    parts.append("外向(E)" if c[0] == "E" else "内向(I)")
    parts.append("实感(S)" if c[1] == "S" else "直觉(N)")
    parts.append("思考(T)" if c[2] == "T" else "情感(F)")
    parts.append("判断(J)" if c[3] == "J" else "知觉(P)")
    return f"{c}（{' · '.join(parts)}）"
