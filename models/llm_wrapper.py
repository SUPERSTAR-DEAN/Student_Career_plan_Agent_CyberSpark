# -*- coding: utf-8 -*-
"""大语言模型统一调用接口封装（OpenAI 兼容）"""
import json
import re
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


CAREER_CONSULT_SYSTEM_PROMPT = """你是「大学生职业规划网」的实时职业咨询顾问，面向中国大学生，语气专业、友善、务实。

职责：
1. 根据用户描述，给出可执行的职业发展建议（方向、能力、实习/项目、学业与求职节奏等），避免空泛鸡汤。
2. 若用户给出的信息不足以做出可靠判断，必须明确说明「当前已知信息不足」或类似表述，并主动提出 1～3 个具体追问（例如年级、专业、城市偏好、已有实习/项目、目标行业岗位等），帮助补全上下文。
3. 不要编造用户未提供的履历细节；不确定时说明依据有限并追问。
4. 回复使用简体中文；可适当分点，但不要输出 JSON 或代码块，除非用户明确要求。"""


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
            # 避免网络异常时长时间挂起，导致前端一直显示「正在思考」
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=120.0,
            )

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
        sys0 = ((messages[0] or {}).get("content") or "") if messages else ""
        if "实时职业咨询" in sys0:
            last = messages[-1] if messages else {}
            user_text = (last.get("content") or "").strip()
            if len(user_text) < 15:
                return (
                    "当前已知信息不足，我还无法给出针对性建议。\n\n"
                    "为更好帮助你，请补充：1）年级与专业；2）更倾向的城市或是否接受异地；3）目前是否有实习/项目经历，以及你大致的职业兴趣方向。"
                )
            return (
                "（演示模式：未配置 API Key，以下为示例回复）\n\n"
                "根据你目前描述，可先明确短期目标（如本学期完成 1 个与目标岗位相关的项目或实习），并同步梳理简历上的成果量化表述。\n\n"
                "若你希望我更精准地建议投递方向与能力缺口，请补充：目标行业/岗位类型、可实习时间段、已掌握的技能栈。"
            )
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
                "mbti_type": "",
            }, ensure_ascii=False, indent=2)
        if "证书匹配判定" in content:
            return json.dumps({
                "match_rate": 65,
                "matched_certs": ["英语四级"],
                "missing_certs": [],
                "reason": "（模拟）部分证书与要求匹配。",
            }, ensure_ascii=False)
        if "实习经历" in content and "岗位实习" in content:
            return json.dumps({
                "match_rate": 58,
                "reason": "（模拟）经历与岗位有一定相关性。",
            }, ensure_ascii=False)
        if "专业技能匹配专家" in content:
            return json.dumps({
                "match_rate": 62,
                "matched_skills": ["Python"],
                "missing_skills": ["Redis"],
                "reason": "（模拟）核心技能部分覆盖岗位要求。",
            }, ensure_ascii=False)
        if "职业素养" in content and "岗位素养要求" in content:
            return json.dumps({
                "match_rate": 70,
                "matched_items": ["沟通", "协作"],
                "missing_items": [],
                "reason": "（模拟）素养维度整体尚可。",
            }, ensure_ascii=False)
        if "学生潜力" in content and "岗位潜力要求" in content:
            return json.dumps({
                "match_rate": 68,
                "matched_items": ["学习能力"],
                "missing_items": [],
                "reason": "（模拟）学习与创新潜力与岗位基本契合。",
            }, ensure_ascii=False)
        if "人岗匹配分析报告" in content:
            return json.dumps({
                "text_report": "（模拟报告）综合匹配处于中等水平，建议补足岗位强调的关键技能并积累对口实践。",
                "structured": {
                    "overall_summary": "匹配中等",
                    "advantages": "基础面尚可",
                    "missing_skills": "部分硬技能待补",
                    "improve_points": "项目与实习",
                    "suggestions": "完成1~2个相关项目并投递实习",
                    "final_advice": "保持学习节奏，针对性投递",
                },
            }, ensure_ascii=False)
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
        """从职位描述中提取结构化岗位要求画像（不少于10个维度）"""
        prompt = """你是一个资深HR专家和职业规划顾问。根据下面的【职位描述】，全面深入地提取岗位要求画像，严格输出一个JSON对象，不要其他解释。

要求：
1. 分析要全面、详细、专业，每个字段都要给出具体、丰富的描述
2. 即使职位描述中没有明确提到某些维度，也要基于岗位性质和行业常识进行合理推断
3. 描述要具体、可操作，避免空洞的表述
4. 对编程语言要严格区分，不要把 C/C++、Java、Python 混为同一技能
5. 若职位描述出现明确语言栈（如 C++/Java/Python），professional_skills 必须包含该语言
6. 若岗位属于下列轨道，请优先提取对应技能：
   - 前端：JavaScript/TypeScript/HTML/CSS/React/Vue
   - 后端：Java/Python/Go、接口设计、数据库、缓存
   - 数据库：SQL、MySQL/Oracle/PostgreSQL、索引、事务、性能优化
   - 科研/研究：算法、机器学习/深度学习、论文阅读、实验设计

必须包含以下键（均为英文），值类型按说明填写：
- professional_skills: 数组，专业技能列表，如 ["Python","Java","SQL","数据结构","算法","设计模式"]，至少提取5-10项关键技能
- certificates: 数组，证书要求，如 ["英语四级","软考","计算机二级","驾照"]，基于岗位性质推荐相关证书
- innovation_ability: 字符串，创新能力要求描述，详细说明该岗位对创新能力的具体要求
- learning_ability: 字符串，学习能力要求描述，说明需要学习哪些新技术、新知识
- stress_resistance: 字符串，抗压能力描述，说明工作压力来源和应对要求
- communication: 字符串，沟通能力描述，说明对内对外沟通的具体要求和场景
- internship_experience: 字符串，实习/项目经验要求，说明需要哪些相关经验和项目背景
- teamwork: 字符串，团队协作要求，说明团队合作的具体要求和角色定位
- problem_solving: 字符串，问题解决能力要求，说明需要解决哪些类型的问题和思维方法
- technical_depth: 字符串，技术深度/基础要求描述，详细说明技术深度要求和必备基础

【职位描述】
%s

输出示例：
{
  "professional_skills": ["Python", "Django", "MySQL", "Redis", "数据结构", "算法", "单元测试"],
  "certificates": ["英语四级", "软考初级", "计算机二级"],
  "innovation_ability": "要求具备创新思维，能够提出优化方案和改进建议，参与技术创新项目",
  "learning_ability": "需要快速学习新技术框架和工具，具备持续学习能力，关注行业前沿动态",
  "stress_resistance": "能够承受项目周期压力和多任务并行工作，具备良好的时间管理能力",
  "communication": "需要与产品、设计、测试团队紧密协作，具备良好的沟通表达和文档撰写能力",
  "internship_experience": "具备互联网公司相关实习经验，有完整项目开发经验优先",
  "teamwork": "能够融入敏捷开发团队，积极参与代码评审和技术分享，具备团队协作精神",
  "problem_solving": "能够独立分析和解决复杂技术问题，具备良好的逻辑思维和调试能力",
  "technical_depth": "具备扎实的计算机基础知识，深入理解数据结构和算法，熟悉分布式系统原理"
}

只输出一个JSON对象，不要任何其他文字解释。"""
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
- mbti_type: 字符串，四字母大写如 "INFJ"；仅当简历或自述中明确写出 MBTI/性格类型时填写，否则填空字符串 ""

若原文未提及某维度，可给合理推断值。只输出一个JSON对象。

【简历/自述】
%s"""
        out = self._call([{"role": "user", "content": prompt % (resume_text or "无")}])
        data = self._parse_json_block(out)
        if isinstance(data, list):
            data = {}
        return data

    def career_consult_chat(self, messages: list[dict]) -> str:
        """多轮职业咨询对话：系统提示词约束下调用 LLM。"""
        sys_msg = {
            "role": "system",
            "content": CAREER_CONSULT_SYSTEM_PROMPT + "\n\n（内部标记：实时职业咨询）",
        }
        thread: list[dict] = [sys_msg]
        for m in messages:
            role = m.get("role")
            text = (m.get("content") or "").strip()
            if role not in ("user", "assistant") or not text:
                continue
            thread.append({"role": role, "content": text})
        if len(thread) < 2:
            return "请先输入你的问题或情况描述。"
        return self._call(thread, temperature=0.45, max_tokens=2000)

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
        """大模型判断学生证书与岗位证书匹配度，返回 match_rate 等（add 文件夹能力并入）。"""
        sc = json.dumps(student_certs or [], ensure_ascii=False)
        jc = json.dumps(job_required_certs or [], ensure_ascii=False)
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
        out = self._call([{"role": "user", "content": prompt % (sc, jc)}], temperature=0.1)
        data = self._parse_json_block(out)
        if not isinstance(data, dict):
            data = {}
        if "match_rate" not in data:
            data["match_rate"] = 50
        return data

    def match_internship(self, student_internship: list, job_requirement: str) -> dict:
        """大模型判断实习经历与岗位经验要求的匹配度。"""
        si = json.dumps(student_internship or [], ensure_ascii=False)
        jr = job_requirement or "无明确要求"
        prompt = """你是专业HR，仅根据【学生实习经历】和【岗位实习/经验要求】判断匹配度，严格输出JSON。

输出必须包含：
- match_rate: 0~100 数字（实习内容与岗位的相关匹配率）
- reason: 简短匹配理由

【学生实习经历】
%s

【岗位实习/经验要求】
%s

仅输出JSON，不要多余文字。"""
        out = self._call([{"role": "user", "content": prompt % (si, jr)}], temperature=0.1)
        data = self._parse_json_block(out)
        if not isinstance(data, dict):
            data = {}
        if "match_rate" not in data:
            data["match_rate"] = 50
        return data

    def match_skills(self, student_skills: list, job_required_skills: list) -> dict:
        """大模型判断职业技能匹配度。"""
        ss = json.dumps(student_skills or [], ensure_ascii=False)
        js = json.dumps(job_required_skills or [], ensure_ascii=False)
        prompt = """你是专业技能匹配专家，严格对比【学生掌握的技能】和【岗位要求技能】，计算匹配率（0~100）。
严格输出JSON，不要多余文字。

关键规则（必须遵守）：
1) 编程语言按“强约束”匹配：Python/Java/C/C++/Go/JavaScript/TypeScript 不可互相替代。
2) 若岗位要求 C/C++，学生仅有 Python/Java，语言项视为未匹配。
3) 仅当存在明确同义词时可视为匹配：如 C++≈CPP，JavaScript≈JS，TypeScript≈TS。
4) 通用能力（如沟通、团队协作）不计入 professional_skills 匹配率。
5) match_rate 要和 matched_skills/missing_skills 一致，不要给“泛化高分”。

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
        out = self._call([{"role": "user", "content": prompt % (ss, js)}], temperature=0.1)
        data = self._parse_json_block(out)
        if not isinstance(data, dict):
            data = {}
        if "match_rate" not in data:
            data["match_rate"] = 50
        return data

    def match_quality(self, student_quality: dict, job_quality: dict) -> dict:
        """大模型判断职业素养匹配度。"""
        sq = json.dumps(student_quality or {}, ensure_ascii=False)
        jq = json.dumps(job_quality or {}, ensure_ascii=False)
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
        out = self._call([{"role": "user", "content": prompt % (sq, jq)}], temperature=0.1)
        data = self._parse_json_block(out)
        if not isinstance(data, dict):
            data = {}
        if "match_rate" not in data:
            data["match_rate"] = 50
        return data

    def match_potential(self, student_potential: dict, job_potential: dict) -> dict:
        """大模型判断发展潜力匹配度。"""
        sp = json.dumps(student_potential or {}, ensure_ascii=False)
        jp = json.dumps(job_potential or {}, ensure_ascii=False)
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
        out = self._call([{"role": "user", "content": prompt % (sp, jp)}], temperature=0.1)
        data = self._parse_json_block(out)
        if not isinstance(data, dict):
            data = {}
        if "match_rate" not in data:
            data["match_rate"] = 50
        return data

    def generate_dual_format_gap_report(
        self,
        student_dim: Any,
        job_dim: Any,
        dimension_scores: Any,
        overall_score: Any,
    ) -> dict:
        """同时生成富文本报告 + 结构化 JSON（与 add 文件夹一致）。"""
        prompt = f"""你是专业职业规划导师，根据下面信息生成一份【人岗匹配分析报告】。

要求：
1. 报告详细、专业、现代化，300~600字，段落自然流畅。
2. 包含：综合评价、优势亮点、缺失技能、待提升维度、改进建议、适配总结。
3. 语言正式、易读、适合学生查看。

【学生信息】
{json.dumps(student_dim, ensure_ascii=False, default=str)}

【岗位要求】
{json.dumps(job_dim, ensure_ascii=False, default=str)}

【维度得分】
{json.dumps(dimension_scores, ensure_ascii=False, default=str)}

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
            res = self._call([{"role": "user", "content": prompt}], temperature=0.3)
            m = re.search(r"\{[\s\S]*\}", res)
            if m:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return self._default_dual_report()

    def _default_dual_report(self) -> dict:
        return {
            "text_report": "报告生成中，请稍后再试。你可以根据各维度得分逐步提升技能与实践经验。",
            "structured": {
                "overall_summary": "暂未生成",
                "advantages": "暂未生成",
                "missing_skills": "暂未生成",
                "improve_points": "暂未生成",
                "suggestions": "暂未生成",
                "final_advice": "暂未生成",
            },
        }
