# Agent Learning Lab

个人学习项目，目标是从零掌握 Agent 工程核心技能。

## 技术栈

- **语言**: Python 3.12+
- **LLM API**: DeepSeek OpenAI-compatible Chat Completions（通过 `httpx` 调用）
- **依赖管理**: pip + requirements.txt
- **环境变量**: python-dotenv，密钥存放于 `.env`

## 项目结构

```
src/
  main.py              # 入口 & 核心逻辑
  tests/               # 测试
requirements.txt
.env                   # DEEPSEEK_API_KEY
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

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 配置密钥
echo "DEEPSEEK_API_KEY=your-key" > .env

# 运行
python src/main.py
```

## 详细文档
- 设计文档 -> 'Docs/design-docs/'
- 执行文档 -> 'Docs/exec-plans/'

## 使用规则
- 只读取与当前任务相关的文档
- 不要一次性加载所有内容
- 信息冲突时，以更具体的文档为准