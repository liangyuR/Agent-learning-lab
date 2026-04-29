可以。接下来一周不要按 Day 切，直接设一个整体目标更好。

# 接下来一周总目标

把当前已经跑通的 **单工具 Agent**，升级成一个：

> **具备多工具调用、统一错误处理、基础日志、可回归测试的 CLI Tool Agent v0.3**

---

# 本周完成标准

## 1. 工具能力扩展

至少支持 3 个工具：

| 工具                          | 作用             |
| --------------------------- | -------------- |
| `get_current_time`          | 查询当前时间         |
| `read_markdown_file`        | 读取 Markdown 文件 |
| `http_get` 或 `query_sqlite` | 请求网页 / 查询本地数据库 |

建议优先顺序：

```text
get_current_time → read_markdown_file → query_sqlite → http_get
```

如果时间有限，做到前三个即可。

---

## 2. 工具调用链标准化

你要把这条链路封装稳定：

```text
用户输入
→ LLM 输出 ToolCallResponse
→ parse / validate
→ ToolCallRequest
→ registry 查找工具
→ arguments 二次校验
→ 执行工具
→ ToolResult
→ 输出结果
```

重点是：**主流程不要散落在 main.py 里**。

建议形成：

```python
def handle_tool_call(tool_req: ToolCallRequest) -> ToolResult:
    ...
```

或者：

```python
class AgentRunner:
    def run(self, user_input: str) -> str:
        ...
```

---

## 3. 统一错误处理

本周必须补齐错误路径。

至少覆盖：

| 错误类型          | 处理方式                   |
| ------------- | ---------------------- |
| JSON 解析失败     | 返回清晰错误                 |
| schema 校验失败   | 返回清晰错误                 |
| 工具不存在         | `ToolResult(ok=False)` |
| 参数缺失 / 类型错误   | `ToolResult(ok=False)` |
| 文件不存在         | `ToolResult(ok=False)` |
| SQL / HTTP 异常 | `ToolResult(ok=False)` |

核心标准：

> 任何异常都不能直接把程序炸掉。

---

## 4. 工具选择 Prompt 固化

你需要整理一版稳定 prompt，让模型知道：

* 有哪些工具
* 每个工具什么时候用
* 必须输出 JSON
* 不允许输出额外自然语言
* 不确定时直接 final_answer，而不是乱调工具

建议 prompt 里明确写：

```text
你只能输出 JSON。
当需要工具时，输出 action=tool_call。
当不需要工具时，输出 action=final_answer。
不要输出 markdown。
不要输出解释。
```

---

## 5. 最小日志

不用上复杂日志系统，先做到这几个字段即可：

```text
[USER] 用户输入
[LLM_RAW] 模型原始输出
[PARSED] 解析后的 action
[TOOL_CALL] 工具名 + 参数
[TOOL_RESULT] ok / error
```

这对排查问题非常关键。

---

## 6. 回归测试样例

准备至少 10 条测试输入，手动或脚本跑都可以。

建议覆盖：

```text
1. 现在 UTC 几点？
2. 现在北京时间几点？
3. 读取 README.md 并总结
4. 读取一个不存在的文件
5. 查询数据库里有哪些设备
6. 输入一个不需要工具的普通问题
7. 故意让模型调用不存在的工具
8. 参数类型错误
9. HTTP 请求一个正常 URL
10. HTTP 请求一个错误 URL
```

---

# 本周最终产出

本周结束时，你应该有：

```text
agent-learning-lab/
├─ src/
│  ├─ main.py
│  ├─ models.py
│  ├─ parser.py
│  ├─ agent_runner.py
│  ├─ tool_registry.py
│  └─ tools/
│     ├─ base.py
│     ├─ time_tool.py
│     ├─ file_tool.py
│     ├─ sqlite_tool.py
│     └─ http_tool.py
├─ tests/
│  └─ manual_cases.md
└─ README.md
```

---

# 本周最重要的技术目标

不是“工具越多越好”，而是这三个：

## 1. 工具协议稳定

所有工具都遵循：

```text
input_model → run(args) → dict
```

然后统一包装成：

```text
ToolResult
```

---

## 2. 错误路径稳定

成功路径能跑只是 demo。
错误路径不崩，才是工程。

---

## 3. 模型输出稳定

你的 Agent 不能依赖“模型刚好听话”。

必须通过：

* schema
* parser
* validator
* fallback error

来约束它。

---

# 本周验收标准

你可以用这几条判断是否完成：

* `get_current_time` 正常可用
* `read_markdown_file` 正常可用
* 至少再有一个 `query_sqlite` 或 `http_get`
* 工具不存在不会崩
* 参数错误不会崩
* 模型输出非法 JSON 有明确错误
* 所有工具结果统一成 `ToolResult`
* README 里有使用示例
* 有 10 条测试样例
* 能演示 3 个不同工具被正确调用

---

# 一句话目标

本周目标就是：

> 把“能调用一个工具的 demo”，升级成“结构清晰、错误可控、可扩展的多工具 CLI Agent”。
