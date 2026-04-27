# -*- coding: utf-8 -*-
"""基于 AI 的大学生职业规划智能体 - Streamlit  Web 界面"""
# 直接运行 python app.py 时，用子进程启动 Streamlit，避免 Runtime 重复创建
if __name__ == "__main__":
    import os
    import sys
    if os.environ.get("STREAMLIT_LAUNCHED_BY_APP") != "1":
        import subprocess
        env = {**os.environ, "STREAMLIT_LAUNCHED_BY_APP": "1"}
        sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__, "--server.headless", "true"], env=env))

from pathlib import Path
import base64
import html
import streamlit as st
import plotly.graph_objects as go

# 优先加载 .env，便于使用千问 API Key
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from config import AppConfig

AppConfig.ensure_dirs()

st.set_page_config(page_title="大学生职业规划智能体", page_icon="📋", layout="wide")


def _get_wallpaper_base64() -> str:
    """读取 assets 中的壁纸图片并转为 base64，用于 CSS 背景。

    为了避免文件名和后缀（如 .png.jpg）反复修改带来的问题：
    - 优先查找文件名中包含 'wallpaper' 的图片
    - 支持 .png / .jpg / .jpeg 等常见格式
    - 若未找到，则回退为任意一张图片
    """
    base_dir = Path(__file__).resolve().parent / "assets"
    img_path = None
    if base_dir.exists():
        # 先找名字里带 wallpaper 的
        candidates = list(base_dir.glob("*wallpaper*"))
        # 如果没找到，再退回所有常见图片格式
        if not candidates:
            candidates = list(base_dir.glob("*.png")) + list(base_dir.glob("*.jpg")) + list(base_dir.glob("*.jpeg"))
        if candidates:
            img_path = candidates[0]
    if img_path is None:
        return ""
    try:
        data = img_path.read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        return ""


def _inject_global_style():
    """全局样式：以插画壁纸为主背景，并叠加轻微动态效果和卡片式内容区。"""
    b64 = _get_wallpaper_base64()
    bg_image_css = (
        f"url('data:image/png;base64,{b64}')"
        if b64
        else "linear-gradient(120deg, #fff4e6, #ffe0cc, #ffd1dc)"  # 若找不到图片则退回渐变色
    )
    st.markdown(
        f"""
        <style>
        /* 整体背景：使用插画壁纸为主背景，增加更明显的“缓慢推近 + 轻微平移”动态效果 */
        .stApp {{
            background-image: {bg_image_css};
            background-position: center top;
            background-size: cover;
            background-attachment: fixed;
            animation: bgZoom 18s ease-in-out infinite alternate;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
        }}

        @keyframes bgZoom {{
            0% {{
                background-size: 100% 100%;
                background-position: center top;
                filter: brightness(1);
            }}
            50% {{
                background-size: 108% 108%;
                background-position: center 10%;
                filter: brightness(1.05);
            }}
            100% {{
                background-size: 115% 115%;
                background-position: center 20%;
                filter: brightness(1.03);
            }}
        }}

        /* 让主体内容区域居中一些，四周留白更多，像一张“职业规划卡片” */
        .main .block-container {{
            padding-top: 2.5rem;
            padding-bottom: 3rem;
            max-width: 1120px;
        }}

        /* 中央内容卡片：提高透明度，让壁纸更明显 */
        .career-main-card {{
            background: rgba(255, 255, 255, 0.65);
            border-radius: 18px;
            padding: 12px 28px 24px 28px;
            box-shadow: 0 18px 45px rgba(255, 153, 102, 0.25);
            border: 1px solid rgba(255, 173, 128, 0.45);
            backdrop-filter: blur(10px);
        }}

        /* 顶部 Hero 模块 */
        .career-hero {{
            margin-bottom: 0.5rem;
        }}

        /* 标题与正文统一用更醒目的深色，保证在壁纸上清晰可读 */
        .career-title h1, .career-title h2, .career-title h3 {{
            color: #222222;
        }}
        .career-subtitle {{
            color: #333333;
            font-size: 0.95rem;
        }}
        .stMarkdown, .stText, p, label, span, li {{
            color: #222222;
        }}

        /* 侧边栏：半透明暖色背景 */
        [data-testid="stSidebar"] {{
            background: rgba(255, 255, 255, 0.9);
            border-right: 1px solid rgba(255, 173, 128, 0.35);
        }}

        /* 输入组件整体风格：圆角 + 更高透明度白底 + 暖色边框
           使用更高优先级的选择器，覆盖 Streamlit 默认样式 */
        textarea, input[type="text"], .stTextInput input, .stTextArea textarea {{
            border-radius: 10px !important;
            border: 1px solid rgba(255, 173, 128, 0.7) !important;
            background-color: rgba(255, 255, 255, 0.20) !important;
            color: #111111 !important;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.06) !important;
        }}

        /* 外层 input/textarea/select 容器默认也是纯白，这里一起调成半透明 */
        div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"],
        .stTextInput>div>div, .stTextArea>div>div, .stTextArea>div>div>textarea,
        .stSelectbox, .stSelectbox>div, .stSelectbox>div>div,
        .stMultiSelect, .stMultiSelect>div, .stMultiSelect>div>div,
        div[role="combobox"] {{
            background-color: rgba(255, 255, 255, 0.10) !important;
        }}
        textarea:focus, input[type="text"]:focus, .stTextInput input:focus {{
            outline: none !important;
            border-color: #ff7a45 !important;
            box-shadow: 0 0 0 1px rgba(255, 122, 69, 0.5) !important;
        }}

        /* 小节标题下方添加细分割线，增强信息分组感 */
        .section-title {{
            margin-top: 0.75rem;
            margin-bottom: 0.3rem;
            font-weight: 600;
            color: #704d3a;
        }}
        .section-title::after {{
            content: "";
            display: block;
            width: 64px;
            height: 3px;
            border-radius: 999px;
            margin-top: 4px;
            background: linear-gradient(90deg, #ff9f68, #ff7a45);
        }}

        /* 结果区：轻量卡片和时间轴风格的路径展示 */
        .career-result-card {{
            background: rgba(255, 255, 255, 0.92);
            border-radius: 14px;
            padding: 18px 20px;
            margin-top: 10px;
            border: 1px solid rgba(255, 173, 128, 0.25);
        }}

        /* 报告展示区：更大、更清晰的半透明阅读面板 */
        .report-panel {{
            background: rgba(255, 255, 255, 0.82);
            border-radius: 16px;
            padding: 20px 22px;
            margin-top: 8px;
            border: 1px solid rgba(255, 173, 128, 0.45);
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.08);
            backdrop-filter: blur(8px);
        }}
        .report-panel h4 {{
            margin: 0 0 10px 0;
            color: #1f2937;
            font-size: 1.15rem;
            font-weight: 700;
        }}
        .report-panel-text {{
            color: #1f2937;
            font-size: 1.04rem;
            line-height: 1.85;
            font-weight: 560;
            letter-spacing: 0.1px;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .career-timeline {{
            position: relative;
            margin-left: 10px;
            padding-left: 18px;
        }}
        .career-timeline::before {{
            content: "";
            position: absolute;
            left: 4px;
            top: 0;
            bottom: 0;
            width: 2px;
            background: linear-gradient(#ffb347, #ff7a45);
        }}
        .career-timeline-item {{
            position: relative;
            margin-bottom: 8px;
            padding-left: 6px;
        }}
        .career-timeline-item::before {{
            content: "";
            position: absolute;
            left: -11px;
            top: 4px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #ff7a45;
            box-shadow: 0 0 0 3px rgba(255, 122, 69, 0.25);
        }}

        /* 按钮：圆角暖色调，hover 更亮 */
        .stButton>button {{
            background: linear-gradient(135deg, #ff9f68, #ff7a45);
            color: #fff;
            border-radius: 999px;
            border: none;
            padding: 0.4rem 1.4rem;
            font-weight: 600;
            box-shadow: 0 8px 20px rgba(255, 122, 69, 0.35);
        }}
        .stButton>button:hover {{
            background: linear-gradient(135deg, #ffa96e, #ff8c4f);
            box-shadow: 0 10px 24px rgba(255, 122, 69, 0.5);
        }}

        /* 单选框与 slider 的主色调整为暖橙色 */
        div[role="radiogroup"] label, .stSlider label {{
            color: #704d3a;
            font-weight: 500;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# 缓存系统初始化
@st.cache_resource
def get_system():
    from main import initialize_system
    return initialize_system()


def main_ui():
    _inject_global_style()

    st.markdown(
        """
        <div class="career-hero career-title">
          <h1>📋 基于 AI 的大学生职业规划智能体</h1>
          <p class="career-subtitle">
            面向青年学生，一站式完成自我分析 × 岗位洞察 × 职业路径规划，帮助你看见更清晰、更有把握的未来。
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="career-main-card">', unsafe_allow_html=True)

        data_path = AppConfig.JOB_DATA_PATH
        sample_path = Path(data_path).parent / "job_data_sample.csv"
        if not Path(data_path).exists() and not sample_path.exists():
            st.warning(f"请先准备岗位数据 CSV 并放置于：`{data_path}`。可参考 `data/raw/job_data_sample.csv` 格式。")
            st.markdown("</div>", unsafe_allow_html=True)
            st.stop()

        with st.spinner("正在为你加载职业机会地图，请稍候…"):
            try:
                components = get_system()
            except Exception as e:
                st.error(f"系统初始化失败：{e}")
                st.markdown("</div>", unsafe_allow_html=True)
                st.stop()

    llm, job_profiles, career_graph, matching_engine = components
    st.sidebar.success(f"已加载 {len(job_profiles)} 个岗位")

    input_mode = st.radio("输入方式", ["表单录入", "简历上传"], horizontal=True)

    form_data = {}
    resume_path = None

    # 主体布局：左侧输入表单，右侧预留“即时反馈/说明”区域
    left_col, right_col = st.columns([2.2, 1.3])

    with left_col:
        if input_mode == "简历上传":
            st.markdown('<div class="section-title">上传简历</div>', unsafe_allow_html=True)
            f = st.file_uploader("上传简历（PDF/Word/TXT）", type=["pdf", "docx", "txt"])
            if f:
                save_path = Path(AppConfig.DATA_DIR) / "uploads" / f.name
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(f.getvalue())
                resume_path = str(save_path)
            form_data = {}
        else:
            st.markdown('<div class="section-title">基本信息与能力自评</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                form_data["student_id"] = st.text_input("学号/昵称", value="anonymous")
                form_data["grade"] = st.selectbox("当前年级", ["大一", "大二", "大三", "大四", "研究生", "其他"], index=1)
                form_data["major_direction"] = st.text_input("专业方向（如：计算机科学、软件工程）", value="")
                form_data["school_tier"] = st.selectbox(
                    "院校层次（用于竞争力评分）",
                    ["未填写", "985/双一流", "211/双一流", "普通一本/二本", "高职/专科"],
                    index=0,
                )
                skills_raw = st.text_area("专业技能（每行一个，如 Python、SQL、Java）")
                form_data["professional_skills"] = [s.strip() for s in (skills_raw or "").split("\n") if s.strip()]
                form_data["certificates"] = st.text_input("已获证书（逗号分隔）", value="").replace("，", ",").split(",")
                form_data["certificates"] = [s.strip() for s in form_data["certificates"] if s.strip()]
            with c2:
                form_data["target_industry"] = st.multiselect(
                    "感兴趣的行业（可多选）",
                    ["互联网", "软件开发", "大数据/AI", "金融科技", "制造业数字化", "其他"],
                )
                form_data["target_city"] = st.text_input("优先就业城市（如：北京/上海/深圳）", value="")
                form_data["learning_ability"] = st.slider("学习能力 1-5", 1, 5, 3)
                form_data["communication"] = st.slider("沟通能力 1-5", 1, 5, 3)
                form_data["stress_resistance"] = st.slider("抗压能力 1-5", 1, 5, 3)
                form_data["innovation_ability"] = st.slider("创新能力 1-5", 1, 5, 3)
                form_data["teamwork"] = st.slider("团队协作 1-5", 1, 5, 3)
                form_data["problem_solving"] = st.slider("问题解决 1-5", 1, 5, 3)
                form_data["technical_depth"] = st.slider("技术深度 1-5", 1, 5, 3)
            exp_raw = st.text_area(
                "项目/实习经历（每段一行）",
                placeholder="例如：2024.07-2024.09 XX公司 · 后端实习生 —— 负责接口开发与单元测试等",
            )
            form_data["experience"] = [s.strip() for s in (exp_raw or "").split("\n") if s.strip()]

            awards_raw = st.text_area(
                "竞赛/奖项经历（每段一行）",
                placeholder="例如：省级一等奖（计算机设计大赛）\n国家级三等奖（挑战杯）",
            )
            form_data["awards_experience"] = [s.strip() for s in (awards_raw or "").split("\n") if s.strip()]

            research_raw = st.text_area(
                "科研/论文/专利经历（每段一行）",
                placeholder="例如：SCI一作论文1篇\n发明专利1项\n国家级课题参与",
            )
            form_data["research_experience"] = [s.strip() for s in (research_raw or "").split("\n") if s.strip()]

    with right_col:
        st.markdown(
            """
            <div class="career-result-card">
              <div class="section-title">小贴士</div>
              <p style="font-size:0.9rem; color:#704d3a;">
                建议尽量用具体、量化的描述填写技能和项目，例如：
                “独立完成××系统的接口开发并通过单元测试”，这样生成的能力画像和匹配结果会更准确。
              </p>
              <p style="font-size:0.9rem; color:#704d3a;">
                如有明确目标岗位，也可以在左侧侧边栏填写，将更聚焦地规划你的职业路径。
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    top_k = st.sidebar.slider("推荐岗位数量", 5, 20, 10)
    use_ai_match = st.sidebar.checkbox(
        "使用大模型增强匹配（六维 AI 子项打分 + 双格式差距报告，较慢且需 API Key）",
        value=False,
    )
    target_jobs = st.sidebar.text_input("目标岗位（可选，逗号分隔）", value="").replace("，", ",").split(",")
    target_jobs = [s.strip() for s in target_jobs if s.strip()]

    if st.button("生成职业规划报告"):
        if not resume_path and not form_data.get("professional_skills") and not form_data.get("experience"):
            st.warning("请至少填写技能或经历，或上传简历。")
        else:
            with st.spinner("正在分析并生成报告..."):
                from main import process_student_career_planning
                # 将额外基础信息汇总到 career_preferences 中，便于后续画像与路径规划使用
                career_prefs = {
                    "grade": form_data.get("grade"),
                    "major_direction": form_data.get("major_direction"),
                    "target_industry": form_data.get("target_industry"),
                    "target_city": form_data.get("target_city"),
                    "school_tier": form_data.get("school_tier"),
                }
                form_data["career_preferences"] = career_prefs
                student_input = {
                    "form_data": form_data,
                    "resume_path": resume_path,
                    "target_jobs": target_jobs,
                    "top_k": top_k,
                    "use_ai": use_ai_match,
                }
                result = process_student_career_planning(student_input, components)
            st.session_state["career_result"] = result

    if st.session_state.get("career_result"):
        result = st.session_state["career_result"]
        profile = result["student_profile"]
        report_data = result["report_data"]
        match_results = result["match_results"]
        career_path = result["career_path"]
        action_plan = result["action_plan"]

        st.subheader("一、学生能力画像")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("完整度", f"{getattr(profile, 'completeness_score', 0):.1f}")
        with col_b:
            st.metric("竞争力", f"{getattr(profile, 'competitiveness_score', 0):.1f}")

        st.subheader("二、人岗匹配推荐与维度雷达图")
        for r in match_results[:5]:
            st.write(f"- **{r['job_name']}** — 匹配度 **{r['overall_score']}** 分")

        # 维度雷达图：与匹配引擎一致的六维
        if match_results:
            top_match = match_results[0]
            dim_scores = top_match.get("dimension_scores", {})
            dim_keys = [
                "basic_requirements",
                "professional_skills",
                "communication_teamwork",
                "stress_problem_solving",
                "learning_ability",
                "innovation_ability",
            ]
            dim_labels = ["基础要求", "职业技能", "沟通协作", "抗压与问题解决", "学习能力", "创新能力"]
            scores = [dim_scores.get(k, 0) for k in dim_keys]
            fig = go.Figure()
            fig.add_trace(
                go.Scatterpolar(
                    r=scores + scores[:1],
                    theta=dim_labels + dim_labels[:1],
                    fill="toself",
                    name="匹配度",
                    line=dict(color="#ff7a45"),
                )
            )
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 100], showline=False, gridcolor="rgba(0,0,0,0.1)"),
                    bgcolor="rgba(255,255,255,0.0)",
                ),
                showlegend=False,
                margin=dict(l=40, r=40, t=40, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("三、职业路径规划")
        st.write("**短期目标：**", career_path.get("short_term", ""))
        mid_pts = career_path.get("mid_term_paths") or []
        st.write(
            "**中期路径：**",
            "、".join(str(x) for x in mid_pts) if mid_pts else "（暂无）",
        )
        st.write("**长期愿景：**", career_path.get("long_term_vision", ""))

        # 针对 Top1 岗位，展示垂直晋升路径与换岗路径（基于职业图谱）
        try:
            from models.graph_builder import CareerGraphBuilder  # 仅用于类型提示

            top_job_id = match_results[0].get("job_id") if match_results else None
            if top_job_id and hasattr(career_graph, "get_vertical_paths") and hasattr(career_graph, "get_lateral_paths"):
                job_profiles = getattr(career_graph, "job_profiles", {})
                vertical_paths = career_graph.get_vertical_paths(top_job_id) or []
                lateral_paths = career_graph.get_lateral_paths(top_job_id) or []

                def _name(jid: str) -> str:
                    jp = job_profiles.get(jid)
                    return getattr(jp, "job_name", jid) if jp else jid

                st.markdown("**垂直晋升示例路径：**")
                if vertical_paths:
                    for path in vertical_paths[:3]:
                        names = " → ".join(_name(j) for j in path)
                        st.write(f"- {names}")
                else:
                    st.write("- （当前岗位暂无明显的垂直晋升路径数据）")

                st.markdown("**可考虑的横向换岗方向：**")
                if lateral_paths:
                    for path in lateral_paths[:5]:
                        if len(path) >= 2:
                            st.write(f"- {_name(path[0])} → {_name(path[1])}")
                else:
                    st.write("- （当前岗位暂无换岗路径数据）")
        except Exception:
            pass

        st.subheader("四、行动计划")
        short_lines = "\n".join(
            [f"• {t.get('task', '')}（{t.get('deadline', '')}）" for t in action_plan.get("short_term", [])]
        ) or "（暂无短期行动建议）"
        mid_lines = "\n".join(
            [f"• {t.get('task', '')}（{t.get('deadline', '')}）" for t in action_plan.get("mid_term", [])]
        ) or "（暂无中期行动建议）"
        plan_text = (
            f"【短期计划】\n{short_lines}\n\n"
            f"【中期计划】\n{mid_lines}\n\n"
            f"【评估周期】\n{action_plan.get('evaluation_cycle', '每月复盘一次')}"
        )
        plan_text = html.escape(plan_text)
        st.markdown(
            f"""
            <div class="report-panel">
              <h4>行动计划（清晰阅读版）</h4>
              <div class="report-panel-text">{plan_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("报告摘要")
        summary_text = report_data.get("executive_summary", "") or "（暂无报告摘要）"
        summary_text = html.escape(summary_text)
        st.markdown(
            f"""
            <div class="report-panel">
              <h4>生成报告摘要</h4>
              <div class="report-panel-text">{summary_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("导出 Word"):
                out = Path(AppConfig.DATA_DIR) / "reports" / "career_report.docx"
                out.parent.mkdir(parents=True, exist_ok=True)
                from models.report_generator import CareerReportGenerator
                gen = CareerReportGenerator()
                if gen.export_to_word(report_data, str(out)):
                    st.success(f"已保存：{out}")
                else:
                    st.error("导出失败")
        with col2:
            if st.button("导出 PDF"):
                out = Path(AppConfig.DATA_DIR) / "reports" / "career_report.pdf"
                out.parent.mkdir(parents=True, exist_ok=True)
                from models.report_generator import CareerReportGenerator
                gen = CareerReportGenerator()
                if gen.export_to_pdf(report_data, str(out)):
                    st.success(f"已保存：{out}")
                else:
                    st.error("导出失败（若缺少中文字体可能失败）")


if __name__ == "__main__":
    main_ui()

