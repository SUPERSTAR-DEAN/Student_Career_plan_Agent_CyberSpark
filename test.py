import os
from dotenv import load_dotenv  # <--- 1. 导入
from dashscope import Generation

# <--- 2. 【关键】显式加载当前目录下的 .env 文件
# 这行代码会强制读取 .env 并注入到环境变量中
load_dotenv() 

# 现在的 os.getenv 一定能读到了！
api_key = os.getenv("DASHSCOPE_API_KEY")

if not api_key:
    print("❌ 错误：仍未读取到 API Key。请检查 .env 文件内容。")
else:
    print(f"✅ 成功读取 Key: {api_key[:8]}...")
    
    messages = [
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': '你是谁？'}
    ]
    
    response = Generation.call(
        api_key=api_key, 
        model="qwen-plus",   
        messages=messages,
        result_format="message"
    )

    if response.status_code == 200:
        print(response.output.choices[0].message.content)
    else:
        print(f"HTTP返回码：{response.status_code}")
        print(f"错误信息：{response.message}")