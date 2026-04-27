# 基于 AI 的大学生职业规划智能体

面向高校学生的职业规划智能体：支持岗位画像构建、学生能力画像、人岗匹配与职业生涯发展报告生成。

## 功能概览

- **就业岗位要求画像**：不少于 10 个维度（专业技能、证书、创新能力、学习能力、抗压能力、沟通能力、实习能力、团队协作、问题解决、技术深度）；垂直晋升路径与横向换岗路径图谱（至少 5 个岗位各不少于 2 条换岗路径）。
- **学生就业能力画像**：支持简历上传或表单录入，经大模型解析为能力画像，并给出完整度与竞争力评分。
- **职业生涯发展报告**：人岗匹配（基础要求、职业技能、职业素养、发展潜力四维加权）、职业目标与路径规划、分阶段行动计划、报告润色与导出（Word/PDF）。

## 环境要求

- Python 3.10+
- 至少一个大语言模型 API（OpenAI 兼容接口，如 OpenAI、通义千问等）

## 安装与配置

```bash
# 克隆或进入项目目录
cd Student_Career_plan_Agent

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量：复制 .env.example 为 .env，填写 API Key 等
copy .env.example .env
# 编辑 .env，设置 LLM_API_KEY、LLM_MODEL_NAME、可选 LLM_BASE_URL（如使用通义等）
```

## 岗位数据

- 将企业提供的岗位数据 CSV 放在 `data/raw/job_data.csv`。
- CSV 需包含列（中文）：职位编码、职位名称、工作地址、薪资范围、公司全称、所属行业、人员规模、企业性质、职位描述、公司简介。
- 若无 `job_data.csv`，程序会尝试使用同目录下的 `job_data_sample.csv` 作为演示数据。

## 运行方式

### Web 界面（推荐）

```bash
streamlit run app.py
```

浏览器打开提示的地址（通常 http://localhost:8501），可：

1. 选择「表单录入」或「简历上传」；
2. 填写能力自评或上传 PDF/Word 简历；
3. 点击「生成职业规划报告」；
4. 查看匹配结果、职业路径、行动计划，并导出 Word/PDF。

### 命令行

```bash
python main.py
```

会执行一次系统初始化并用量例表单做一次报告生成演示。

## 项目结构

```
├── config.py              # 全局配置（路径、权重、维度）
├── main.py                # 入口：initialize_system、process_student_career_planning
├── app.py                 # Streamlit Web 界面
├── models/
│   ├── llm_wrapper.py     # 大模型调用封装（OpenAI 兼容）
│   ├── job_profile.py     # 岗位画像与 JobProfileBuilder
│   ├── graph_builder.py   # 职业图谱（垂直/横向）
│   ├── student_profile.py # 学生画像与 StudentProfileAnalyzer
│   ├── matching_engine.py # 人岗匹配引擎（四维加权）
│   └── report_generator.py# 报告生成与导出
├── services/
│   ├── data_processor.py  # 岗位 CSV 加载
│   └── resume_parser.py   # 简历文本解析（PDF/Word/TXT）
├── data/
│   ├── raw/               # job_data.csv / job_data_sample.csv
│   ├── graphs/            # 导出的职业图谱
│   └── reports/           # 导出的报告
└── requirements.txt
```

## 技术要求与指标说明

- **大模型**：至少使用一个大语言模型，用于岗位画像生成、学生画像解析、人岗匹配辅助、报告摘要与建议。
- **人岗匹配**：从基础要求、职业技能、职业素养、发展潜力四个维度加权打分；职业技能维度侧重关键技能匹配，设计上支持关键技能匹配准确率不低于 80%。
- **岗位/学生画像**：通过 LLM 抽取与规则归一化，关键信息以结构化维度存储，便于抽样评估（目标关键信息准确率 >90%）。
- **报告**：建议可操作、可解释；支持智能润色、完整性检查与手动编辑（在导出的 Word 中修改后保存即可）。

## 许可证

按项目约定使用。
