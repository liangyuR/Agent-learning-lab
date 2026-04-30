第 3 周最终产出
一个多轮 CLI Agent

具备：

支持 session
保存消息历史
能读取当前上下文
能更新任务状态
能进行简单历史裁剪
能生成 summary memory
仍然保留第 2 周的工具调用能力
建议你先做的最小版本

不要一上来做数据库持久化。
先用本地 JSON 文件即可：

.sessions/
├─ test001.json
├─ autocharge-plan.json
└─ default.json

每个 session 里保存：

{
  "session_id": "test001",
  "summary": "",
  "messages": [],
  "variables": {}
}
第 3 周一句话目标

从“单轮能调工具”，升级到“多轮能记住上下文，并基于上下文继续完成任务”。