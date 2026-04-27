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

from models.job_profile import JobProfile, is_computer_related_job


# 层级关键词：(关键词元组, 层级0~5)
LEVEL_KEYWORDS = [
    (("实习", "实习生"), 0),
    (("初级", "助理", "见习"), 1),
    (("中级", "工程师", "专员", "设计师"), 2),
    (("高级", "资深", "主管", "高级工程师"), 3),
    (("专家", "架构师", "经理", "组长"), 4),
    (("总监", "首席", "负责人", "主任"), 5),
]


def _normalize_job_title_for_merge(job_name: str, fallback_id: str) -> str:
    """用于可视化去重：同一展示名称合并为一个节点。"""
    t = (job_name or "").strip()
    t = " ".join(t.split())
    t = t.lower()
    return t if t else str(fallback_id)


def _choose_canonical_job_id(ids: list[str], preferred: set[str]) -> str:
    """优先保留锚点中的 id，否则取字典序最小的稳定代表。"""
    for x in ids:
        if x in preferred:
            return x
    return min(ids)


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


def _skill_similarity_pair(sk_a: list, sk_b: list) -> float:
    """对称技能相似度 0~1，用于可视化补边；双方无技能时给极小正值便于排序。"""
    sa = [s.lower().strip() for s in (sk_a or []) if s and str(s).strip()]
    sb = [s.lower().strip() for s in (sk_b or []) if s and str(s).strip()]
    if not sa and not sb:
        return 0.02
    if not sa or not sb:
        return 0.0
    set_a, set_b = set(sa), set(sb)
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return float(inter) / float(union) if union else 0.0


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
        """构建横向换岗路径（基于技能相似度），每岗约 4 条出边（略丰富即可）。"""
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
        lateral_cap = 4

        def try_add_lateral(u: str, v: str) -> bool:
            """仅当 u->v 尚无边时添加换岗边，避免覆盖已存在的垂直晋升边。"""
            if G.has_edge(u, v):
                return False
            G.add_edge(u, v, type="lateral", label="换岗")
            return True

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
                if added >= lateral_cap:
                    break
                if try_add_lateral(p.job_id, qid):
                    added += 1
            if added < lateral_cap:
                for q in profiles_list:
                    if added >= lateral_cap:
                        break
                    if p.job_id == q.job_id:
                        continue
                    if try_add_lateral(p.job_id, q.job_id):
                        added += 1
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
        """获取某岗位的垂直晋升路径（多条，按展示名称去重，避免同一路径重复出现）"""
        G = self.graph
        if G is None:
            return []
        jid = self._resolve_job_id(job_id)
        if not jid or jid not in G:
            return []
        out = []
        seen_names: set[tuple[str, str]] = set()
        for succ in G.successors(jid):
            edge = G.edges.get((jid, succ), {})
            if edge.get("type") != "vertical":
                continue
            na = str(G.nodes[jid].get("job_name", jid))
            nb = str(G.nodes[succ].get("job_name", succ))
            key = (na, nb)
            if key in seen_names:
                continue
            seen_names.add(key)
            out.append([jid, succ])
        return out

    def get_lateral_paths(self, job_id: str) -> list[list[str]]:
        """获取某岗位的横向换岗路径（按展示名称去重）"""
        G = self.graph
        if G is None:
            return []
        jid = self._resolve_job_id(job_id)
        if not jid or jid not in G:
            return []
        out = []
        seen_names: set[tuple[str, str]] = set()
        for succ in G.successors(jid):
            edge = G.edges.get((jid, succ), {})
            if edge.get("type") != "lateral":
                continue
            na = str(G.nodes[jid].get("job_name", jid))
            nb = str(G.nodes[succ].get("job_name", succ))
            key = (na, nb)
            if key in seen_names:
                continue
            seen_names.add(key)
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

    def export_focus_visualization(self, anchor_job_ids: list[str], *, computer_only: bool = True) -> dict[str, Any]:
        """导出面向前端的「垂直晋升 + 换岗」双子图（节点规模可控）。

        - 默认仅包含计算机 / IT 相关岗位（与全库 1w 条数据一致，但展示时过滤）。
        - 垂直：多种子沿全库 vertical 边扩展；导出时对同名展示名合并为一点并去重边。
        - 换岗：略作丰富；同名合并。
        """
        G = self.graph
        if G is None or nx is None:
            return {
                "vertical": {"nodes": [], "edges": []},
                "lateral": {"nodes": [], "edges": []},
                "anchors_resolved": [],
            }

        def jid_ok(x: str) -> bool:
            return bool(x) and x in G

        def node_profile(nid: str) -> Optional[JobProfile]:
            return G.nodes[nid].get("profile")

        def is_cs(nid: str) -> bool:
            if not computer_only:
                return True
            return is_computer_related_job(node_profile(nid))

        cs_nids_sorted: list[str] = sorted(
            (n for n in G.nodes if is_cs(n)),
            key=lambda x: str(G.nodes[x].get("job_name", x)),
        )

        resolved: list[str] = []
        for raw in anchor_job_ids:
            rid = self._resolve_job_id(str(raw).strip()) or str(raw).strip()
            if jid_ok(rid) and rid not in resolved and (not computer_only or is_cs(rid)):
                resolved.append(rid)

        anchors: list[str] = list(resolved)
        anchor_target = 20
        for jid in self.job_profiles.keys():
            if len(anchors) >= anchor_target:
                break
            if jid_ok(jid) and is_cs(jid) and jid not in anchors:
                anchors.append(jid)
        if len(anchors) < anchor_target:
            for nid in cs_nids_sorted:
                if len(anchors) >= anchor_target:
                    break
                if nid not in anchors:
                    anchors.append(nid)

        lateral_anchors = anchors[:6]
        if not lateral_anchors and cs_nids_sorted:
            lateral_anchors = cs_nids_sorted[:6]
        center: Optional[str] = None
        for c in resolved:
            if jid_ok(c) and is_cs(c):
                center = c
                break
        if center is None:
            for c in lateral_anchors:
                if jid_ok(c) and is_cs(c):
                    center = c
                    break
        if center is None and cs_nids_sorted:
            center = cs_nids_sorted[0]

        # ---------- 垂直子图：全库层级边 + 多种子 BFS；每条招聘独立成点；按种子边预算避免首种子占满 ----------
        v_nodes: set[str] = set()
        v_edges: list[dict[str, Any]] = []
        v_edge_keys: set[tuple[str, str]] = set()
        max_up, max_down = 5, 5
        v_branch_cap = 110
        per_seed_vert_budget = 950
        global_vert_cap = 14000

        center_prof = node_profile(center) if center else None
        ref_skills = list(getattr(center_prof, "required_skills", None) or []) if center_prof else []

        def _rank_vertical_neighbors(nids: list[str]) -> list[str]:
            if len(nids) <= v_branch_cap:
                return nids
            if not ref_skills:
                return sorted(nids, key=lambda x: str(G.nodes[x].get("job_name", x)))[:v_branch_cap]
            scored: list[tuple[str, float]] = []
            for vid in nids:
                pb = node_profile(vid)
                sk = getattr(pb, "required_skills", None) or [] if pb else []
                scored.append((vid, _skill_similarity_pair(ref_skills, sk)))
            scored.sort(key=lambda x: -x[1])
            return [x[0] for x in scored[:v_branch_cap]]

        def expand_vertical_from(seed: Optional[str]) -> None:
            if not seed or not jid_ok(seed) or not is_cs(seed):
                return
            edge_stop = min(len(v_edges) + per_seed_vert_budget, global_vert_cap)

            def add_vertical_edge(frm: str, to: str) -> None:
                if frm == to or not jid_ok(frm) or not jid_ok(to):
                    return
                if not is_cs(frm) or not is_cs(to):
                    return
                if len(v_edges) >= edge_stop:
                    return
                ek = (frm, to)
                if ek in v_edge_keys:
                    return
                v_edge_keys.add(ek)
                v_nodes.add(frm)
                v_nodes.add(to)
                v_edges.append({"from": frm, "to": to, "arrows": "to", "label": "晋升", "dashes": False})

            v_nodes.add(seed)
            frontier = [(seed, 0)]
            seen_bfs: set[tuple[str, int]] = set()
            while frontier:
                if len(v_edges) >= edge_stop:
                    break
                u, depth = frontier.pop(0)
                if depth >= max_up or (u, depth) in seen_bfs:
                    continue
                seen_bfs.add((u, depth))
                succ = [
                    v
                    for v in G.successors(u)
                    if is_cs(v) and G.edges.get((u, v), {}).get("type") == "vertical"
                ]
                for v in _rank_vertical_neighbors(succ):
                    add_vertical_edge(u, v)
                    frontier.append((v, depth + 1))
            frontier = [(seed, 0)]
            seen_bfs2: set[tuple[str, int]] = set()
            while frontier:
                if len(v_edges) >= edge_stop:
                    break
                u, depth = frontier.pop(0)
                if depth >= max_down or (u, depth) in seen_bfs2:
                    continue
                seen_bfs2.add((u, depth))
                pred = [
                    v
                    for v in G.predecessors(u)
                    if is_cs(v) and G.edges.get((v, u), {}).get("type") == "vertical"
                ]
                for v in _rank_vertical_neighbors(pred):
                    add_vertical_edge(v, u)
                    frontier.append((v, depth + 1))

        v_seeds: list[str] = []
        if center and jid_ok(center) and is_cs(center):
            v_seeds.append(center)
        for c in resolved:
            if jid_ok(c) and is_cs(c) and c not in v_seeds:
                v_seeds.append(c)
        for a in anchors:
            if len(v_seeds) >= 18:
                break
            if jid_ok(a) and is_cs(a) and a not in v_seeds:
                v_seeds.append(a)
        if not v_seeds and lateral_anchors:
            s0 = lateral_anchors[0]
            if jid_ok(s0) and is_cs(s0):
                v_seeds.append(s0)
        for s in v_seeds[:18]:
            expand_vertical_from(s)

        # 子图内仍无晋升边连接的节点：从全图补一条 vertical（不改动换岗部分）
        deg_v: dict[str, int] = {}
        for e in v_edges:
            deg_v[e["from"]] = deg_v.get(e["from"], 0) + 1
            deg_v[e["to"]] = deg_v.get(e["to"], 0) + 1

        def add_vertical_edge_global(frm: str, to: str) -> bool:
            if frm == to or not jid_ok(frm) or not jid_ok(to):
                return False
            if not is_cs(frm) or not is_cs(to):
                return False
            if len(v_edges) >= global_vert_cap:
                return False
            ek = (frm, to)
            if ek in v_edge_keys:
                return False
            v_edge_keys.add(ek)
            v_nodes.add(frm)
            v_nodes.add(to)
            v_edges.append({"from": frm, "to": to, "arrows": "to", "label": "晋升", "dashes": False})
            deg_v[frm] = deg_v.get(frm, 0) + 1
            deg_v[to] = deg_v.get(to, 0) + 1
            return True

        repairs = 0
        for nid in list(v_nodes):
            if repairs >= 400:
                break
            if deg_v.get(nid, 0) > 0:
                continue
            for w in G.successors(nid):
                if not is_cs(w):
                    continue
                if G.edges.get((nid, w), {}).get("type") != "vertical":
                    continue
                if add_vertical_edge_global(nid, w):
                    repairs += 1
                break
            if deg_v.get(nid, 0) > 0:
                continue
            for w in G.predecessors(nid):
                if not is_cs(w):
                    continue
                if G.edges.get((w, nid), {}).get("type") != "vertical":
                    continue
                if add_vertical_edge_global(w, nid):
                    repairs += 1
                break

        # ---------- 换岗子图：略作丰富（少锚点、适中出边）----------
        l_nodes: set[str] = set()
        l_edges: list[dict[str, Any]] = []
        edge_keys: set[tuple[str, str]] = set()
        max_lateral_per_anchor = 5
        min_lateral_per_anchor = 2
        neighbor_pool_limit = 320
        neighbor_pool = cs_nids_sorted[:neighbor_pool_limit]

        def add_lateral(a: str, b: str) -> None:
            if a == b or not jid_ok(a) or not jid_ok(b):
                return
            if computer_only and (not is_cs(a) or not is_cs(b)):
                return
            key = (a, b)
            if key in edge_keys:
                return
            edge_keys.add(key)
            l_nodes.add(a)
            l_nodes.add(b)
            l_edges.append({"from": a, "to": b, "arrows": "to", "label": "换岗", "dashes": True})

        def lateral_out_count(aid: str) -> int:
            return sum(1 for e in l_edges if e["from"] == aid)

        def ranked_skill_neighbors(src_id: str, exclude: set[str], cap: int) -> list[str]:
            pa = node_profile(src_id)
            sk_a = getattr(pa, "required_skills", None) or [] if pa else []
            scored: list[tuple[str, float]] = []
            for bid in neighbor_pool:
                if bid == src_id or bid in exclude:
                    continue
                if not is_cs(bid):
                    continue
                pb = node_profile(bid)
                sk_b = getattr(pb, "required_skills", None) or [] if pb else []
                scored.append((bid, _skill_similarity_pair(sk_a, sk_b)))
            scored.sort(key=lambda x: -x[1])
            return [x[0] for x in scored[:cap]]

        for aid in lateral_anchors:
            if not jid_ok(aid) or not is_cs(aid):
                continue
            l_nodes.add(aid)
            outs: list[str] = []
            for succ in G.successors(aid):
                if not is_cs(succ):
                    continue
                ed = G.edges.get((aid, succ), {})
                if ed.get("type") == "lateral":
                    outs.append(succ)
            for succ in outs[:max_lateral_per_anchor]:
                add_lateral(aid, succ)
            if lateral_out_count(aid) < min_lateral_per_anchor:
                have_to = {e["to"] for e in l_edges if e["from"] == aid}
                ranked = ranked_skill_neighbors(aid, {aid} | have_to, max_lateral_per_anchor + 60)
                for bid in ranked:
                    if lateral_out_count(aid) >= max_lateral_per_anchor:
                        break
                    add_lateral(aid, bid)
            if lateral_out_count(aid) < min_lateral_per_anchor:
                used = {e["to"] for e in l_edges if e["from"] == aid}
                for other in lateral_anchors:
                    if lateral_out_count(aid) >= min_lateral_per_anchor:
                        break
                    if other == aid or not is_cs(other) or other in used:
                        continue
                    before = lateral_out_count(aid)
                    add_lateral(aid, other)
                    if lateral_out_count(aid) > before:
                        used.add(other)
            if lateral_out_count(aid) < min_lateral_per_anchor:
                used = {e["to"] for e in l_edges if e["from"] == aid}
                for jid in cs_nids_sorted:
                    if lateral_out_count(aid) >= min_lateral_per_anchor:
                        break
                    if jid == aid or jid in used:
                        continue
                    before = lateral_out_count(aid)
                    add_lateral(aid, jid)
                    if lateral_out_count(aid) > before:
                        used.add(jid)

        def pack_nodes(nid_set: set[str]) -> list[dict[str, Any]]:
            out = []
            for nid in sorted(nid_set, key=lambda x: str(G.nodes[x].get("job_name", x))):
                out.append(
                    {
                        "id": nid,
                        "label": str(G.nodes[nid].get("job_name", nid))[:24],
                        "title": str(G.nodes[nid].get("job_name", nid)),
                    }
                )
            return out

        def collapse_duplicate_titles(
            nid_set: set[str],
            edges: list[dict[str, Any]],
            preferred_ids: set[str],
        ) -> tuple[set[str], list[dict[str, Any]]]:
            """同名岗位合并为单一节点，边映射到代表 job_id 并去重。"""
            if not nid_set:
                return nid_set, edges
            groups: dict[str, list[str]] = {}
            for nid in nid_set:
                if nid not in G.nodes:
                    continue
                title = str(G.nodes[nid].get("job_name", nid) or nid)
                key = _normalize_job_title_for_merge(title, nid)
                groups.setdefault(key, []).append(nid)
            canon: dict[str, str] = {}
            for _gkey, ids in groups.items():
                uniq = list(dict.fromkeys(ids))
                canon.update({x: _choose_canonical_job_id(uniq, preferred_ids) for x in uniq})
            new_nodes = set(canon.values())
            seen_e: set[tuple[str, str]] = set()
            new_edges: list[dict[str, Any]] = []
            for e in edges:
                a = canon.get(e["from"], e["from"])
                b = canon.get(e["to"], e["to"])
                if a == b:
                    continue
                ek = (a, b)
                if ek in seen_e:
                    continue
                seen_e.add(ek)
                ne = dict(e)
                ne["from"], ne["to"] = a, b
                new_edges.append(ne)
            return new_nodes, new_edges

        preferred = set(resolved)
        # 垂直：同名岗位合并为一点，减少重复、连线更清晰；换岗同样合并
        v_nodes, v_edges = collapse_duplicate_titles(v_nodes, v_edges, preferred)
        l_nodes, l_edges = collapse_duplicate_titles(l_nodes, l_edges, preferred)

        return {
            "vertical": {"nodes": pack_nodes(v_nodes), "edges": v_edges},
            "lateral": {"nodes": pack_nodes(l_nodes), "edges": l_edges},
            "anchors_resolved": lateral_anchors,
            "computer_only": computer_only,
        }
