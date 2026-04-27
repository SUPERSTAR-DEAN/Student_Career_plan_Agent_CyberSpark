# -*- coding: utf-8 -*-
"""职业发展路径图谱构建器（垂直晋升 + 横向换岗）"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

try:
    import networkx as nx
except ImportError:
    nx = None

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.job_profile import JobProfile


# 层级关键词：(关键词元组, 层级0~5)
LEVEL_KEYWORDS = [
    (("实习", "实习生"), 0),
    (("初级", "助理", "见习"), 1),
    (("中级", "工程师", "专员", "设计师"), 2),
    (("高级", "资深", "主管", "高级工程师"), 3),
    (("专家", "架构师", "经理", "组长"), 4),
    (("总监", "首席", "负责人", "主任"), 5),
]


def _infer_level(job_name: str) -> int:
    """根据岗位名称推断层级 0~5"""
    name = (job_name or "").lower()
    for keywords, level in LEVEL_KEYWORDS:
        for k in keywords:
            if k in name:
                return level
    return 2  # 默认中级


def _skill_overlap(a: list, b: list) -> float:
    """计算两组技能的交集占比（基于 a 的视角）"""
    if not a:
        return 0.0
    sa, sb = set(s.lower().strip() for s in a if s), set(s.lower().strip() for s in b if s)
    if not sa:
        return 0.0
    return len(sa & sb) / len(sa)


class CareerGraphBuilder:
    """职业发展路径图谱构建器"""

    def __init__(self):
        self.graph = None  # nx.DiGraph
        self.job_profiles: dict[str, JobProfile] = {}
        self._job_name_to_id: dict[str, str] = {}

    def build_vertical_path(self, job_profiles: dict[str, JobProfile]) -> None:
        """构建垂直晋升路径图谱（基于岗位层级关系）"""
        if nx is None:
            self.graph = None
            return
        self.job_profiles = dict(job_profiles)
        self._job_name_to_id = {p.job_name: jid for jid, p in job_profiles.items()}
        G = nx.DiGraph()
        profiles_list = list(job_profiles.values())
        for p in profiles_list:
            G.add_node(p.job_id, job_name=p.job_name, level=_infer_level(p.job_name), profile=p)
        for i, p in enumerate(profiles_list):
            level_i = _infer_level(p.job_name)
            for q in profiles_list:
                if p.job_id == q.job_id:
                    continue
                level_q = _infer_level(q.job_name)
                if level_q == level_i + 1:
                    G.add_edge(p.job_id, q.job_id, type="vertical", label="晋升")
        self.graph = G

    def build_lateral_path(self, job_profiles: Optional[dict[str, JobProfile]] = None) -> None:
        """构建横向换岗路径（基于技能相似度），保证至少5个岗位各有不少于2条换岗路径"""
        if nx is None:
            return
        if job_profiles is not None:
            self.job_profiles = dict(job_profiles)
            if self.graph is None:
                self.build_vertical_path(job_profiles)
        G = self.graph
        if G is None:
            return
        profiles_list = list(self.job_profiles.values())
        for i, p in enumerate(profiles_list):
            candidates = []
            for q in profiles_list:
                if p.job_id == q.job_id:
                    continue
                overlap = _skill_overlap(p.required_skills, q.required_skills)
                if overlap > 0 or (not p.required_skills and not q.required_skills):
                    candidates.append((q.job_id, overlap))
            candidates.sort(key=lambda x: -x[1])
            added = 0
            for qid, _ in candidates:
                if not G.has_edge(p.job_id, qid) or G.edges[p.job_id, qid].get("type") != "lateral":
                    G.add_edge(p.job_id, qid, type="lateral", label="换岗")
                    added += 1
                    if added >= 2:
                        break
            if added < 2 and len(candidates) >= 2:
                for qid, _ in candidates[added:2]:
                    if not G.has_edge(p.job_id, qid):
                        G.add_edge(p.job_id, qid, type="lateral", label="换岗")
                        added += 1
                        if added >= 2:
                            break
            # 保证至少 2 条换岗路径：若不足则从任意其他岗位补足
            if added < 2:
                for q in profiles_list:
                    if p.job_id == q.job_id:
                        continue
                    if not G.has_edge(p.job_id, q.job_id) or G.edges[p.job_id, q.job_id].get("type") != "lateral":
                        G.add_edge(p.job_id, q.job_id, type="lateral", label="换岗")
                        added += 1
                        if added >= 2:
                            break
        self.graph = G

    def get_career_path(self, start_job: str, target_job: Optional[str] = None) -> list:
        """获取从起始岗位到目标岗位的发展路径（节点 id 列表）。start_job 可为 job_id 或 job_name"""
        G = self.graph
        if G is None:
            return []
        start_id = self._resolve_job_id(start_job)
        target_id = self._resolve_job_id(target_job) if target_job else None
        if not start_id or start_id not in G:
            return []
        if target_id:
            if target_id not in G:
                return []
            try:
                return nx.shortest_path(G, start_id, target_id)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return []
        return list(nx.dfs_preorder_nodes(G, start_id))[:20]

    def get_vertical_paths(self, job_id: str) -> list[list[str]]:
        """获取某岗位的垂直晋升路径（多条）"""
        G = self.graph
        if G is None:
            return []
        jid = self._resolve_job_id(job_id)
        if not jid or jid not in G:
            return []
        out = []
        for succ in G.successors(jid):
            edge = G.edges.get((jid, succ), {})
            if edge.get("type") == "vertical":
                out.append([jid, succ])
        return out

    def get_lateral_paths(self, job_id: str) -> list[list[str]]:
        """获取某岗位的横向换岗路径（至少2条）"""
        G = self.graph
        if G is None:
            return []
        jid = self._resolve_job_id(job_id)
        if not jid or jid not in G:
            return []
        out = []
        for succ in G.successors(jid):
            edge = G.edges.get((jid, succ), {})
            if edge.get("type") == "lateral":
                out.append([jid, succ])
        return out

    def _resolve_job_id(self, job_ref: Optional[str]) -> Optional[str]:
        if not job_ref:
            return None
        job_ref = job_ref.strip()
        if job_ref in self.job_profiles:
            return job_ref
        return self._job_name_to_id.get(job_ref)

    def export_graph(self, output_path: Optional[str] = None, json_path: Optional[str] = None) -> None:
        """导出图谱为 GML 和/或 JSON"""
        G = self.graph
        if G is None:
            return
        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                nx.write_gml(G, p, stringizer=str)
            except Exception:
                nx.write_gml(G, str(p))
        if json_path:
            data = {
                "nodes": [{"id": n, "label": G.nodes[n].get("job_name", n)} for n in G.nodes],
                "edges": [{"source": u, "target": v, "type": G.edges[u, v].get("type", "")} for u, v in G.edges],
            }
            Path(json_path).parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def visualize_graph(self, job_category: Optional[str] = None) -> Any:
        """可视化特定领域的职业路径图谱（返回可展示的数据，前端用）"""
        G = self.graph
        if G is None:
            return {"nodes": [], "edges": []}
        nodes = [{"id": n, "label": G.nodes[n].get("job_name", n)} for n in G.nodes]
        edges = [{"source": u, "target": v, "type": G.edges[u, v].get("type", "")} for u, v in G.edges]
        return {"nodes": nodes, "edges": edges}
    
# ====================== 按参考图风格重写的可视化测试（完全对齐参考图）======================
if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams["font.sans-serif"] = ["SimHei"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120
    plt.rcParams["figure.figsize"] = (14, 8)

    # 1. 构造和参考图完全对应的岗位数据（层级0-5，3条职业线：开发/数据/设计/管理）
    # 层级0（实习）
    job0_1 = JobProfile("job0_1", "实习工程师(SE)")
    job0_1.required_skills = ["Python", "Java", "数据结构"]
    job0_2 = JobProfile("job0_2", "实习数据分析师(DS)")
    job0_2.required_skills = ["SQL", "Excel", "Python"]

    # 层级1（初级/助理）
    job1_1 = JobProfile("job1_1", "助理工程师(SE)")
    job1_1.required_skills = ["Python", "Java", "Git"]
    job1_2 = JobProfile("job1_2", "初级数据分析师(DS)")
    job1_2.required_skills = ["SQL", "Python", "Pandas"]

    # 层级2（中级/工程师）
    job2_1 = JobProfile("job2_1", "软件工程师(SE)")
    job2_1.required_skills = ["Java", "Spring", "MySQL"]
    job2_2 = JobProfile("job2_2", "数据分析师(DS)")
    job2_2.required_skills = ["SQL", "Python", "Tableau"]
    job2_3 = JobProfile("job2_3", "UX设计师(Design)")
    job2_3.required_skills = ["Figma", "PS", "交互设计"]

    # 层级3（高级/资深）
    job3_1 = JobProfile("job3_1", "高级工程师(SE)")
    job3_1.required_skills = ["架构", "性能优化", "Java"]
    job3_2 = JobProfile("job3_2", "高级数据分析师(DS)")
    job3_2.required_skills = ["机器学习", "SQL", "Python"]
    job3_3 = JobProfile("job3_3", "高级设计师(Design)")
    job3_3.required_skills = ["UI设计", "用户研究", "Figma"]
    job3_4 = JobProfile("job3_4", "技术组长(Mgt)")
    job3_4.required_skills = ["团队管理", "项目管理", "Java"]

    # 层级4（专家/经理）
    job4_1 = JobProfile("job4_1", "首席工程师(SE)")
    job4_1.required_skills = ["架构设计", "技术选型", "Java"]
    job4_2 = JobProfile("job4_2", "数据架构师(DS)")
    job4_2.required_skills = ["数据仓库", "架构", "SQL"]
    job4_3 = JobProfile("job4_3", "部门经理(Mgt)")
    job4_3.required_skills = ["团队管理", "业务规划", "项目管理"]

    # 层级5（总监/首席）
    job5_1 = JobProfile("job5_1", "技术总监(Mgt)")
    job5_1.required_skills = ["战略规划", "团队管理", "架构"]
    job5_2 = JobProfile("job5_2", "首席架构师(DS)")
    job5_2.required_skills = ["企业架构", "技术战略", "数据治理"]

    # 组装岗位字典
    test_jobs = {
        job0_1.job_id: job0_1, job0_2.job_id: job0_2,
        job1_1.job_id: job1_1, job1_2.job_id: job1_2,
        job2_1.job_id: job2_1, job2_2.job_id: job2_2, job2_3.job_id: job2_3,
        job3_1.job_id: job3_1, job3_2.job_id: job3_2, job3_3.job_id: job3_3, job3_4.job_id: job3_4,
        job4_1.job_id: job4_1, job4_2.job_id: job4_2, job4_3.job_id: job4_3,
        job5_1.job_id: job5_1, job5_2.job_id: job5_2,
    }

    # 2. 构建图谱（完全复用你原有的逻辑）
    builder = CareerGraphBuilder()
    builder.build_vertical_path(test_jobs)
    builder.build_lateral_path()

    # 3. 调用你原有的visualize_graph函数（完全不动）
    graph_data = builder.visualize_graph()
    print(f"✅ 图谱生成成功，节点数：{len(graph_data['nodes'])}，边数：{len(graph_data['edges'])}")

    # ====================== 核心：按参考图风格重写绘图逻辑 ======================
    G = builder.graph
    if G is None:
        print("❌ 图谱为空，无法绘图")
        exit()

    # ---------------------- 步骤1：按层级分层布局（和参考图完全一致的垂直分层） ----------------------
    # 按层级分组
    level_nodes = {}
    for node in G.nodes:
        level = G.nodes[node]["level"]
        if level not in level_nodes:
            level_nodes[level] = []
        level_nodes[level].append(node)
    
    # 为每个层级分配y坐标（层级0在最下方，层级5在最上方，和参考图一致）
    pos = {}
    y_levels = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    for level, nodes in level_nodes.items():
        y = y_levels[level]
        # 同一层级均匀分布x坐标
        x_coords = np.linspace(0.5, len(nodes)+0.5, len(nodes))
        for i, node in enumerate(nodes):
            pos[node] = (x_coords[i], y)

    # ---------------------- 步骤2：按参考图配色 ----------------------
    # 层级对应颜色（和参考图完全一致：绿→浅蓝→深蓝→紫→红）
    level_colors = {
        0: "#2ca02c",    # 实习（绿）
        1: "#42b8f5",    # 初级（浅蓝）
        2: "#1f77b4",    # 中级（深蓝）
        3: "#9467bd",    # 高级（紫）
        4: "#8c564b",    # 专家/经理（深紫）
        5: "#d62728"     # 总监/首席（红）
    }
    node_colors = [level_colors[G.nodes[n]["level"]] for n in G.nodes]

    # ---------------------- 步骤3：分离晋升/换岗边（和参考图完全一致的箭头样式） ----------------------
    vert_edges = [(u, v) for u, v, d in G.edges(data=True) if d["type"] == "vertical"]
    lat_edges = [(u, v) for u, v, d in G.edges(data=True) if d["type"] == "lateral"]

    # ---------------------- 步骤4：绘图 ----------------------
    fig, ax = plt.subplots()

    # 绘制节点
    nx.draw_networkx_nodes(
        G, pos,
        node_color=node_colors,
        node_size=2500,
        alpha=0.9,
        ax=ax
    )

    # 绘制晋升边（蓝色实线箭头，和参考图一致）
    nx.draw_networkx_edges(
        G, pos,
        edgelist=vert_edges,
        edge_color="#1f77b4",
        width=2,
        arrowstyle="->",
        arrowsize=15,
        ax=ax
    )

    # 绘制换岗边（灰色虚线箭头，和参考图一致）
    nx.draw_networkx_edges(
        G, pos,
        edgelist=lat_edges,
        edge_color="#7f7f7f",
        width=1.5,
        style="--",
        arrowstyle="->",
        arrowsize=10,
        ax=ax
    )

    # 绘制节点标签（岗位名称）
    labels = {n: G.nodes[n]["job_name"] for n in G.nodes}
    nx.draw_networkx_labels(
        G, pos, labels,
        font_size=8,
        font_weight="bold",
        font_color="white",
        ax=ax
    )

    # ---------------------- 步骤5：添加层级标注（和参考图左侧的Level 0~5完全一致） ----------------------
    for level, y in y_levels.items():
        ax.text(
            -0.3, y, f"Level {level}",
            fontsize=10,
            fontweight="bold",
            va="center",
            ha="right"
        )

    # ---------------------- 步骤6：添加图例（和参考图右上角完全一致） ----------------------
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D([0], [0], color="#1f77b4", lw=2, label="晋升 (垂直路径)"),
        Line2D([0], [0], color="#7f7f7f", lw=1.5, linestyle="--", label="换岗 (横向路径)"),
        Patch(facecolor="#2ca02c", label="层级0 (实习)"),
        Patch(facecolor="#42b8f5", label="层级1 (初级)"),
        Patch(facecolor="#1f77b4", label="层级2 (中级)"),
        Patch(facecolor="#9467bd", label="层级3 (高级)"),
        Patch(facecolor="#8c564b", label="层级4 (专家/经理)"),
        Patch(facecolor="#d62728", label="层级5 (总监/首席)"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", bbox_to_anchor=(1.15, 1))

    # ---------------------- 步骤7：美化图表（和参考图风格一致） ----------------------
    ax.set_title(
        "职业发展路径图谱 (垂直晋升 + 横向换岗)",
        fontsize=16,
        fontweight="bold",
        pad=20
    )
    ax.set_ylim(-0.5, 5.5)
    ax.set_xlim(-0.5, max([pos[n][0] for n in G.nodes]) + 0.5)
    ax.axis("off")
    plt.tight_layout()
    plt.show()