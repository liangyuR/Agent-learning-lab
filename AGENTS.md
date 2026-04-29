# Agent Learning Lab

个人学习项目，目标是从零掌握 Agent 工程核心技能。

## 技术栈

- **语言**: Python 3.12+
- **LLM API**: DeepSeek OpenAI-compatible Chat Completions（通过 `httpx` 调用）
- **依赖管理**: pip + requirements.txt
- **环境变量**: python-dotenv，密钥存放于 `.env`（已 gitignore）

## 项目结构

```
src/
  main.py              # 入口 & 核心逻辑
  tests/               # 测试
requirements.txt
.env                   # DEEPSEEK_API_KEY（不入库）
```

## 编码规范

- 所有函数必须添加类型注解（参数 + 返回值）
- 入口函数 `main()` 返回 int 退出码（0=成功，非0=失败）
- 错误信息输出到 stderr，正常结果输出到 stdout
- 职责单一：读取输入、构建 prompt、调用模型、解析输出分别为独立函数
- 中文注释和用户提示，代码标识符用英文

## Agent 开发约定

- 每个新的 Agent 能力（tool use、multi-turn、RAG 等）作为独立模块放在 `src/` 下
- Prompt 模板与业务逻辑分离，便于迭代和测试
- 对外部 API 调用统一做异常处理和重试（使用 tenacity）
- 新增功能必须附带 `src/tests/` 下的测试文件

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 配置密钥
echo "DEEPSEEK_API_KEY=your-key" > .env

# 运行
python src/main.py
```

## 学习路线参考

1. 基础 LLM 调用（当前阶段）
2. Multi-turn 对话 & 上下文管理
3. Tool Use / Function Calling
4. RAG（检索增强生成）
5. Multi-Agent 协作
6. Agent 评估与可观测性
