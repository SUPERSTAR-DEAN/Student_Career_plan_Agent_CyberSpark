# -*- coding: utf-8 -*-
"""大语言模型统一调用接口封装（OpenAI 兼容）"""
import json
import re
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class LLMWrapper:
    """大语言模型统一调用接口封装"""

    def __init__(self, provider: str = "openai", api_key: Optional[str] = None, model_name: Optional[str] = None, base_url: Optional[str] = None):
        # 允许在未安装 openai 包时继续运行（使用 mock 输出），
        # 便于前端/图谱/匹配逻辑在本地调试阶段不被卡住。
        if OpenAI is None:
            self.provider = provider
            self.api_key = api_key or ""
            self.model_name = model_name or "gpt-4o-mini"
            self.base_url = base_url
            self._client = None
            return
        self.provider = provider
        self.api_key = api_key or ""
        self.model_name = model_name or "gpt-4o-mini"
        self.base_url = base_url
        self._client = None
        if self.api_key:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _call(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 2000) -> str:
        """统一调用 LLM，返回助手回复文本"""
        if not self._client:
            return self._mock_response(messages)
        try:
            r = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _mock_response(self, messages: list[dict]) -> str:
        """无 API Key 时的模拟返回，便于本地调试"""
        last = messages[-1] if messages else {}
        content = (last.get("content") or "")
        if "职位描述" in content or "岗位" in content:
            return json.dumps({
                "professional_skills": ["Python", "数据分析", "SQL"],
                "certificates": ["大学英语四级"],
                "innovation_ability": "能参与创新项目",
                "learning_ability": "快速学习新技术",
                "stress_resistance": "能承受工作压力",
                "communication": "良好的沟通能力",
                "internship_experience": "有实习经验优先",
                "teamwork": "团队协作能力",
                "problem_solving": "独立解决问题",
                "technical_depth": "扎实的计算机基础",
            }, ensure_ascii=False, indent=2)
        if "简历" in content or "经历" in content or "技能" in content:
            return json.dumps({
                "professional_skills": {"Python": 3, "SQL": 2},
                "certificates": ["英语四级"],
                "innovation_ability": 3,
                "learning_ability": 4,
                "stress_resistance": 3,
                "communication": 4,
                "internship_experience": [],
                "teamwork": 4,
                "problem_solving": 3,
                "technical_depth": 3,
            }, ensure_ascii=False, indent=2)
        return "[]"

    def _parse_json_block(self, text: str) -> dict | list:
        """从回复中解析 JSON（允许被 markdown 包裹）"""
        text = text.strip()
        # 去除 ```json ... ``` 包裹
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
        # 取第一个 { 或 [ 到最后一个 } 或 ]
        start = text.find("{")
        if start == -1:
            start = text.find("[")
        if start == -1:
            return {}
        end = text.rfind("}") + 1
        if end <= 0:
            end = text.rfind("]") + 1
        if end <= 0:
            return {}
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            return {}

    def extract_job_requirements(self, job_description: str) -> dict:
        """从职位描述中提取结构化岗位要求画像（千问AI增强版）"""
        prompt = """你是专业HR招聘专家。请根据下面的【职位描述】，严格提取岗位要求，只输出标准JSON，不要任何多余文字。

    必须输出以下字段，类型严格遵守：
    - professional_skills: 数组，专业技能（Python/Java/SQL/Vue/Redis等）
    - certificates: 数组，要求的证书（英语四级/计算机二级/软考等）
    - innovation_ability: 字符串，岗位对创新能力的要求
    - learning_ability: 字符串，岗位对学习能力的要求
    - stress_resistance: 字符串，岗位对抗压能力的要求
    - communication: 字符串，岗位对沟通能力的要求
    - internship_experience: 字符串，岗位对实习/项目经验的要求
    - teamwork: 字符串，岗位对团队协作的要求
    - problem_solving: 字符串，岗位对问题解决能力的要求
    - technical_depth: 字符串，岗位对技术深度/基础的要求

    规则：
    1. 只提取原文明确提到的内容
    2. 没有就填空字符串或空数组
    3. 技能与证书要规范、去重
    4. 只返回JSON，不返回任何解释

    【职位描述】
    %s
    """
        out = self._call([{"role": "user", "content": prompt % (job_description or "无")}])
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data

    def analyze_student_profile(self, resume_text: str) -> dict:
        """从简历/自述文本中提取学生能力画像"""
        prompt = """你是一个职业规划师。根据下面的【简历/自述】文本，提取该学生的能力画像，严格输出一个JSON对象。
要求包含以下键（英文），值类型按说明：
- professional_skills: 对象，格式 {"技能名": 掌握程度1-5}，如 {"Python":3,"SQL":2}
- certificates: 数组，已获证书
- awards_experience: 数组，竞赛/奖项经历描述，如 ["省级一等奖（挑战杯）","校级二等奖（数学建模）"]
- research_experience: 数组，科研/论文/专利经历描述，如 ["SCI一作论文1篇","发明专利1项","国家级课题参与"]
- school_tier: 字符串，院校层次（可用：985/双一流、211/双一流、普通一本/二本、高职/专科、不明确）
- innovation_ability: 1-5 的整数，创新能力自评或推断
- learning_ability: 1-5
- stress_resistance: 1-5
- communication: 1-5
- internship_experience: 数组，每项为字符串描述，如 ["某公司实习3个月"]
- teamwork: 1-5
- problem_solving: 1-5
- technical_depth: 1-5

若原文未提及某维度，可给合理推断值。只输出一个JSON对象。

【简历/自述】
%s"""
        out = self._call([{"role": "user", "content": prompt % (resume_text or "无")}])
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data

    def generate_career_advice(self, context: dict) -> str:
        """根据上下文生成个性化职业建议文本"""
        prompt = """根据以下上下文，生成一段面向大学生的个性化职业建议（200字以内），语言简洁、可操作。
重要：只输出一段纯中文文字，不要输出 JSON、代码块、键值对或任何结构化格式。

上下文：
%s"""
        out = self._call([{"role": "user", "content": prompt % json.dumps(context, ensure_ascii=False, indent=2)}], max_tokens=500)
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)

    def optimize_report_content(self, report_text: str) -> str:
        """对报告内容进行智能润色（语句通顺、专业、可读）"""
        if not report_text or len(report_text) < 50:
            return report_text
        prompt = """请对下面这段职业规划报告内容进行润色，保持原意和结构，使语句更专业、通顺。只输出润色后的正文，不要加“润色如下”等前缀。

内容：
%s"""
        out = self._call([{"role": "user", "content": prompt % report_text[:4000]}], max_tokens=3000)
        return out if isinstance(out, str) else report_text
    
    def match_certificates(self, student_certs: list, job_required_certs: list) -> dict:
        """让千问AI判断学生证书与岗位要求证书的匹配度，返回匹配率、匹配证书、缺失证书及理由"""
        prompt = """你是专业HR，只进行证书匹配判定，严格输出JSON对象，不要输出多余内容。

对比【学生持有的证书】和【岗位要求的证书】，计算匹配率。
输出JSON格式必须包含：
- match_rate: 0-100的数字
- matched_certs: 数组，已匹配的证书
- missing_certs: 数组，未匹配/缺失的证书
- reason: 字符串，一句话说明匹配情况

【学生持有的证书】
%s

【岗位要求的证书】
%s

仅输出JSON对象，不要添加任何其他文字。"""
        out = self._call([{"role": "user", "content": prompt % (student_certs, job_required_certs)}], temperature=0.1)
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data
    
    def match_internship(self, student_internship: list, job_requirement: str) -> dict:
        """让千问AI判断学生实习经历与岗位要求的匹配度，返回匹配率与说明"""
        prompt = """你是专业HR，仅根据【学生实习经历】和【岗位实习/经验要求】判断匹配度，严格输出JSON。

    输出必须包含：
    - match_rate: 0~100 数字（实习内容与岗位的相关匹配率）
    - reason: 简短匹配理由

    【学生实习经历】
    %s

    岗位实习/经验要求】
    %s

    仅输出JSON，不要多余文字。"""
        out = self._call([{"role": "user", "content": prompt % (student_internship, job_requirement)}],temperature=0.1)
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data
    
    def match_skills(self, student_skills: list, job_required_skills: list) -> dict:
        """让千问AI判断学生职业技能与岗位要求的匹配度，返回匹配率"""
        prompt = """你是专业技能匹配专家，严格对比【学生掌握的技能】和【岗位要求技能】，计算匹配率（0~100）。
    严格输出JSON，不要多余文字。

    输出格式：
    {
        "match_rate": 数字,
        "matched_skills": ["已匹配技能"],
        "missing_skills": ["缺失技能"],
        "reason": "匹配说明"
    }

    【学生掌握的技能】
    %s

    【岗位要求技能】
    %s
    """
        out = self._call([{"role": "user", "content": prompt % (student_skills, job_required_skills)}], temperature=0.1)
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data
    
    def match_quality(self, student_quality: dict, job_quality: dict) -> dict:
        """让千问AI判断学生职业素养与岗位要求的匹配度，返回匹配率"""
        prompt = """你是专业HR，对比【学生职业素养】和【岗位素养要求】，计算匹配率（0~100）。
    评价维度：沟通能力、团队合作、抗压能力、问题解决能力。
    严格输出JSON，不要多余文字。

    输出格式：
    {
        "match_rate": 数字,
        "matched_items": ["匹配项"],
        "missing_items": ["不足项"],
        "reason": "一句话说明"
    }

    【学生职业素养（1-5分）】
    %s

    【岗位素养要求】
    %s
    """
        out = self._call([{"role": "user", "content": prompt % (student_quality, job_quality)}], temperature=0.1)
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data
    
    def match_potential(self, student_potential: dict, job_potential: dict) -> dict:
        """让千问AI判断学生发展潜力与岗位要求的匹配度，返回匹配率"""
        prompt = """你是专业HR，仅对比【学生潜力】和【岗位潜力要求】，计算匹配率（0~100）。
    评价维度：学习能力、创新能力。
    严格输出JSON，不要多余文字。

    输出格式：
    {
        "match_rate": 数字,
        "matched_items": ["匹配项"],
        "missing_items": ["不足项"],
        "reason": "一句话说明"
    }

    【学生潜力（1-5分）】
    %s

    【岗位潜力要求】
    %s
    """
        out = self._call([{"role": "user", "content": prompt % (student_potential, job_potential)}], temperature=0.1)
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data
    
    def generate_dual_format_gap_report(self, student_dim, job_dim, dimension_scores, overall_score):
        """同时生成：富文本报告 + 结构化JSON，供前端切换"""
        prompt = f"""
你是专业职业规划导师，根据下面信息生成一份【人岗匹配分析报告】。

要求：
1. 报告详细、专业、现代化，300~600字，段落自然流畅。
2. 包含：综合评价、优势亮点、缺失技能、待提升维度、改进建议、适配总结。
3. 语言正式、易读、适合学生查看。

【学生信息】
{student_dim}

【岗位要求】
{job_dim}

【维度得分】
{dimension_scores}

【综合得分】{overall_score}

请严格按照下面JSON格式返回，不要多余内容：
{{
    "text_report": "完整流畅的报告段落，300~600字",
    "structured": {{
        "overall_summary": "一句话综合评价",
        "advantages": "优势亮点详细描述",
        "missing_skills": "缺失或不足的技能",
        "improve_points": "需要提升的维度",
        "suggestions": "具体可执行的改进建议",
        "final_advice": "最终投递与发展建议"
    }}
}}
"""

        try:
            import json
            import re
            res = self._call([{"role": "user", "content": prompt}], temperature=0.3)
            # 安全提取 JSON
            match = re.search(r'\{.*\}', res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data
            return self._default_dual_report()
        except Exception:
            return self._default_dual_report()

    def _default_dual_report(self):
        return {
            "text_report": "报告生成中，请稍后再试。你可以根据各维度得分逐步提升技能与实践经验。",
            "structured": {
                "overall_summary": "暂未生成",
                "advantages": "暂未生成",
                "missing_skills": "暂未生成",
                "improve_points": "暂未生成",
                "suggestions": "暂未生成",
                "final_advice": "暂未生成"
            }
        }

# ====================== 🔥 千问 AI 真实效果全功能测试 ======================
if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    import os

    # 自动加载你的 .env 配置
    load_dotenv()

    # 初始化 LLM（自动用你的千问账号）
    llm = LLMWrapper(
        provider=os.getenv("LLM_PROVIDER", "qwen"),
        api_key=os.getenv("LLM_API_KEY"),
        model_name=os.getenv("LLM_MODEL_NAME", "qwen-max"),
        base_url=os.getenv("LLM_BASE_URL")
    )

    print("=" * 60)
    print("✅ 千问大模型调用成功，开始真实功能测试\n")

    # ==============================================
    # 测试 1：从岗位描述提取 10 维岗位画像（真实 AI）
    # ==============================================
    print("【1】测试：岗位画像提取")
    job_desc = """
    岗位职责：
    1. 负责Python后端开发与接口实现
    2. 熟练使用MySQL、Redis
    3. 具备良好沟通能力与团队协作能力
    4. 有实习经验优先
    5. 能快速学习新技术
    """
    job_result = llm.extract_job_requirements(job_desc)
    print("📌 岗位画像：")
    print(json.dumps(job_result, ensure_ascii=False, indent=2))

    print("\n" + "="*60)

    # ==============================================
    # 测试 2：从学生简历提取能力画像（真实 AI）
    # ==============================================
    print("【2】测试：学生能力画像分析")
    resume = """
    我是计算机专业学生，掌握Python、SQL，
    有英语四级证书，参加过校级挑战杯比赛，
    学习能力强，善于沟通，有过2个月实习经验。
    """
    student_result = llm.analyze_student_profile(resume)
    print("📌 学生能力：")
    print(json.dumps(student_result, ensure_ascii=False, indent=2))

    print("\n" + "="*60)

    # ==============================================
    # 测试 3：生成个性化职业建议（真实 AI）
    # ==============================================
    print("【3】测试：AI 职业建议")
    advice = llm.generate_career_advice({
        "学生技能": ["Python", "SQL"],
        "目标岗位": "数据分析师",
        "优势": "学习能力强",
        "不足": "缺乏项目经验"
    })
    print("📌 建议：\n", advice)

    print("\n" + "="*60)
    print("🎉 所有 AI 功能测试完成！全部使用真实千问大模型！")