import sys
import os
from dotenv import load_dotenv

# 加载环境变量（必须！）
load_dotenv()

# 添加项目路径，能找到 models
sys.path.append(".")

# 直接 import 你原来的真实函数
from models.matching_engine import _score_basic  # 如果你文件名不是这个，我会告诉你改


# ======================
# 测试用数据（你提供的两组）
# ======================
if __name__ == "__main__":
    print("===== 测试 1：学生有 Python一级 + 计算机二级 =====")
    student1 = {
        "basic_requirements": {
            "certificates": ["Python一级", "计算机二级"],
            "internship_experience": ["Python开发实习"],
            "technical_depth": 4
        }
    }

    job = {
        "basic_requirements": {
            "certificates": ["Python相关证书"],
            "internship_experience": "开发相关实习"
        }
    }

    score1 = _score_basic(student1, job)
    print("最终基础得分：", score1)

    print("\n===== 测试 2：学生只有 计算机二级（无Python证书） =====")
    student2 = {
        "basic_requirements": {
            "certificates": ["计算机二级"],
            "internship_experience": ["Python开发实习"],
            "technical_depth": 4
        }
    }

    score2 = _score_basic(student2, job)
    print("最终基础得分：", score2)

    print("\n===== 结果对比 =====")
    print("学生1得分：", score1)
    print("学生2得分：", score2)