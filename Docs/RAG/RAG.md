### 参考资料：

[Retrieval-Augmented Generation for Knowledge-Intensive NLP Task](https://arxiv.org/pdf/2005.11401)

[What is Retrieval-Augmented Generation (RAG)?](https://www.youtube.com/watch?v=T-D1OfcDW1M)‘

---

# 什么是 RAG（Retrieval-Augmented Generation）？

我理解的 RAG 是一种模型的上下文工程技术（现在可能称之为 harness 更加合适）。它的主要作用是帮助模型减少幻觉，通过“data”来获取真正的答案。

比如模型训练于 2025 年，那么依靠它本身的参数，必然不可能知道刚刚 26 年发生的事情，但是通过 RAG，它可以通过 web，自有知乎库等等 API，来获取信息回答你。

这样还有一个好处是可以减少它产生的幻觉，避免捏造一个似乎正确的答案来给你。


# Long context VS RAG


### eg1: 当你有两份doc，一份是 release.md 一份 ci.md，然后，其中有一份缺失了安全细则。

如果使用 RAG：

prompt： 补全缺失的安全细则。
Agent：
 - 通过 RAG 找到安全细则
 - 但不知道是谁缺了。因为没有两份完整的文档，RAG 提供的仅是最相关的 chunk。
 - NG...
 - 编一个新的回他算了

--- 

Long context:

prompt： 补全缺失的安全细则 @release.md @ci.md
Agent：
 - 直接将两份文档加入上下文。
 - 对比两份文档
 - 将安全细则从 A 中 cp 到 B
 - End 


### eg2: 重复 Reading

假如有一本员工手册.

Long context:

prompt： 帮我查一下申请物料需要走哪些流程 @员工手册.md
Agent：
 - 读取手册
 - 找到物料相关的信息
 - 总结输出答案

每一次询问，都需要带上整份文件，对 Token 来说很浪费，因为要检索文章，速度也相对较慢

prompt： 帮我查一下申请物料需要走哪些流程
Agent：
 - RAG 提供物料相关的 chunk
 - 总结回答

只有第一次提问时，对该员工手册做一个 clip -> emb -> vectors -> db
之后的每次提问都可以直接通过 RAG 获取 key info