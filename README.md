# Gemini CLI 文本助手

一个最小可运行的 Python CLI 文本助手。  
基于 Gemini API，对输入文本进行分析，并输出固定结构的 JSON 结果。

当前支持：

- 命令行直接输入文本
- 从文件读取文本
- 结构化 JSON 输出
- 模型输出解析与校验
- 基础错误处理
- 模型调用失败自动重试

---

## 功能说明

输入一段文本后，程序会输出以下固定结构：

```json
{
  "summary": "简要总结",
  "key_points": ["要点1", "要点2"],
  "risks": ["风险1", "风险2"],
  "next_actions": ["行动1", "行动2"]
}
```

适合用于：

- 周报总结
- 会议纪要提炼
- 需求描述分析
- 模糊问题整理
- 简单文本分析练习

---

## 项目结构

```text
agent-learning-lab/
├─ src/
│  └─ main.py
├─ samples/
│  ├─ weekly_report.txt
│  ├─ meeting_notes.txt
│  └─ requirement_doc.txt
├─ .env
├─ .gitignore
├─ requirements.txt
└─ README.md
```

---

## 运行环境

- Python 3.10+
- Gemini API Key

---

## 安装依赖

先创建虚拟环境并激活。

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### WSL / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你还没有 `requirements.txt`，可以先写成：

```txt
google-genai
python-dotenv
loguru
tenacity
```

---

## 配置 API Key

在项目根目录创建 `.env` 文件：

```env
GEMINI_API_KEY=your_gemini_api_key
```

也可以使用：

```env
GOOGLE_API_KEY=your_gemini_api_key
```

程序会优先读取：

- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`

---

## 使用方式

### 1. 命令行直接输入文本

```bash
python src/main.py --input "本周完成了自动充电系统的联调测试，机械臂抓取流程已经跑通。"
```

### 2. 从文件读取文本

```bash
python src/main.py --file samples/weekly_report.txt
```

### 3. 交互输入

```bash
python src/main.py
```

然后根据提示输入文本。

---

## 输出说明

程序输出固定 JSON，对应字段如下：

- `summary`：简要总结
- `key_points`：要点列表
- `risks`：风险或注意事项
- `next_actions`：建议的后续行动

如果模型输出不合法，程序会进行解析和校验；当输出不符合约定结构时，会报错并返回非 0 退出码。

---

## 参数说明

### `--input`, `-i`

直接从命令行传入文本内容。

示例：

```bash
python src/main.py -i "请总结这段内容"
```

### `--file`

传入文本文件路径，程序会读取文件内容后进行分析。

示例：

```bash
python src/main.py --file samples/meeting_notes.txt
```

---

## 错误处理

当前已包含以下基础错误处理：

- API Key 缺失检查
- 空输入检查
- 模型输出为空检查
- JSON 解析失败检查
- 输出字段与类型校验
- 模型调用失败自动重试

---

## 已实现的工程能力

- `system instruction` 与 `user content` 分层
- 固定 JSON 输出约束
- 输出合法性校验
- 文件输入支持
- 基础日志打印
- 模型调用重试

---

## 测试样例

建议至少测试以下几类输入：

1. 周报类
2. 会议纪要类
3. 需求描述类
4. 很短输入
5. 模糊 / 低质量输入

你也可以把测试样例整理到单独的 `test_cases.md` 中，方便回归测试。

---

## 当前限制

这是一个第 1 周练习版 CLI 工具，目前仍有这些限制：

- 仅支持单轮分析
- 仅支持单文件输入
- 仅支持固定字段输出
- 尚未加入工具调用
- 尚未加入多轮上下文管理
- 尚未服务化为 API

---

## 下一步计划

- 增加更严格的输出 schema 校验
- 优化模型重试条件，仅对可恢复错误重试
- 支持更多输入格式
- 增加单元测试
- 进入第 2 周：结构化输出与工具调用

---

## 学习目标对应关系

这个项目对应学习路线第 1 周目标：

- 掌握基础大模型调用
- 理解 system / user 内容分层
- 理解结构化输出
- 实现一个最小可运行 CLI 文本助手

---

## License

仅用于学习与实验。

