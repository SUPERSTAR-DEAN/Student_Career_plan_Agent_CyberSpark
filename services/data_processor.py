# -*- coding: utf-8 -*-
"""岗位数据加载与预处理"""
from pathlib import Path
from typing import Optional

import pandas as pd

from config import AppConfig


# CSV 列名映射：支持中文字段名
COLUMNS_MAP = {
    "职位名称": "job_title",
    "工作地址": "location",
    "薪资范围": "salary",
    "公司全称": "company_name",
    "所属行业": "industry",
    "人员规模": "company_size",
    "企业性质": "company_type",
    "职位编码": "job_code",
    "职位描述": "job_description",
    "公司简介": "company_intro",
}

# 兼容你提供的 10000 条岗位 CSV 的表头（如：岗位名称、地址、公司名称、岗位编码、岗位详情 等）
ALT_HEADER_MAP = {
    "岗位名称": "职位名称",
    "地址": "工作地址",
    "公司名称": "公司全称",
    "岗位编码": "职位编码",
    "岗位详情": "职位描述",
}


def load_job_data(csv_path: Optional[Path] = None) -> list[dict]:
    """
    从 CSV 加载岗位数据，返回 list[dict]。
    每条 dict 包含中文键：职位名称、工作地址、薪资范围、公司全称、所属行业、人员规模、企业性质、职位编码、职位描述、公司简介。
    """
    path = Path(csv_path or AppConfig.JOB_DATA_PATH)
    if not path.exists():
        # 演示用：尝试同目录下的 sample
        alt = path.parent / "job_data_sample.csv"
        if alt.exists():
            path = alt
        else:
            return []
    try:
        df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    except Exception:
        try:
            df = pd.read_csv(path, encoding="gbk", on_bad_lines="skip")
        except Exception:
            return []
    # 先将“岗位名称/地址/公司名称/岗位编码/岗位详情”等表头统一为内部使用的中文列名
    df = df.rename(columns=ALT_HEADER_MAP)
    # 再统一为中文列名（兼容此前用英文别名导出的情况）
    rev = {v: k for k, v in COLUMNS_MAP.items()}
    df = df.rename(columns=rev)
    out = []
    for _, row in df.iterrows():
        d = {}
        for cn in COLUMNS_MAP:
            if cn in df.columns:
                v = row.get(cn)
                if pd.isna(v):
                    v = ""
                d[cn] = str(v).strip()
        out.append(d)
    return out


def ensure_job_data_path() -> Path:
    """确保岗位数据文件所在目录存在"""
    AppConfig.ensure_dirs()
    return AppConfig.JOB_DATA_PATH
