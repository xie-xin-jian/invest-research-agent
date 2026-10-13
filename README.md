# 飞书一句话投研 Bot

> 在飞书群里 `@机器人` + 一句话，自动产出结构化投研内容。
> 由 DeepSeek 驱动。

覆盖招聘 JD 的三类职责：

| 一句话指令 | 输出 |
|---|---|
| `@bot 研究下人形机器人行业` | 行业概览 / 头部玩家 / 关键数据 / 风险 / 建议关注（逐字流式更新） |
| `@bot 读研报：[粘贴研报文本]` 或直接发文件 | 核心结论 / 关键数据 / 风险提示 / 适合谁看 |
| `@bot 纪要：[粘贴纪要原文]` | 议题决议 / 行动项 / 待跟进 |
| `@bot 出文档：某行业资料整理` | 群里收到可下载的 Word 文档 |
| 其他闲聊/自由提问 | 投研助手身份自然回答，并提示功能用法 |

## 架构

```
飞书事件订阅 ──► FastAPI webhook ──► 路由器（关键词分流）
                                          ├─ 行业研究  ┐
                                          ├─ 研报速读  ├─ DeepSeek ─► 飞书交互卡片
                                          └─ 纪要结构化 ┘
```

## 目录结构

```
feishu-research-bot/
├── app/
│   ├── main.py             # FastAPI 入口 + 飞书 webhook（事件去重 / 后台处理 / 文件消息分流）
│   ├── feishu_client.py    # 飞书 API 封装（token / 回复 / 卡片 / 文件上传下载）
│   ├── card.py             # Markdown → 飞书交互卡片
│   ├── llm.py              # DeepSeek 调用封装（同步 + 流式）
│   ├── router.py           # 意图路由 → 三个工具 + 通用问答兜底
│   ├── docx_export.py      # Markdown → Word 文档
│   └── tools/
│       ├── industry_research.py   # 场景1：行业研究
│       ├── report_reader.py       # 场景2：研报速读
│       └── meeting_notes.py       # 场景3：会议纪要结构化
├── config.py               # 配置加载（.env）
├── requirements.txt
├── .env.example
└── README.md
```

## 部署步骤

### 1. 准备凭证

**飞书自建应用**（[open.feishu.cn/app](https://open.feishu.cn/app)）：
- 创建企业自建应用，记下 `App ID` / `App Secret`
- 权限管理 → 开通：`im:message`、`im:message.group_at_msg`、`im:message.p2p_msg`（接收消息）、`im:message:send_as_bot`（发送消息）
- 事件订阅 → 请求地址填 `https://<你的公网地址>:8000/feishu/webhook`
- 事件订阅 → 添加事件：`im.message.receive_v1`
- 记下 `Verification Token`（事件订阅页）和 `Encrypt Key`（如有）

**DeepSeek API**（[platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)）：
- 创建 API Key

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入上面的凭证
```

### 3. 安装 & 启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. 内网穿透（本地调试用）

飞书事件订阅需要公网回调。本地调试推荐用 [cpolar](https://www.cpolar.com/) 或 [ngrok](https://ngrok.com/)：

```bash
ngrok http 8000
# 把生成的 https://xxx.ngrok-free.app/feishu/webhook 填回飞书事件订阅
```

### 5. 验证

- 在飞书里搜到机器人，加到群里或私聊
- 发 `研究下人形机器人行业` → 应收到一张绿色标题的结构化卡片

## 演示场景（面试可直接跑）

| 场景 | 测试输入 |
|---|---|
| 行业研究 | `研究下国内新能源车行业` |
| 研报速读 | `读研报：[粘贴一段招股书或研报文本]` |
| 纪要结构化 | `纪要：[粘贴会议纪要原文]` |

## 设计取舍

- **DeepSeek 而非自研模型**：成本可控、中文投研语境效果好、OpenAI 兼容接口接入快。
- **关键词路由而非 LLM 路由**：三场景区分度高，关键词命中即可；避免多一次模型调用，首字延迟更低。
- **Markdown → 飞书卡片**：投研内容表格 / 列表多，飞书 markdown 卡片块原生支持，比拼装复杂 JSON 更易维护。
- **占位卡片 + 更新**：避免长任务让用户以为没响应；先回 `⏳ 正在生成…`，结果到了再 update。

## 工程细节

- **webhook 立即 200 + 后台处理**：飞书要求 3 秒内响应否则重推；配合 `event_id` 幂等去重，一条消息只处理一次。
- **流式生成 + 1s 节流更新卡片**：结果逐字呈现；节流是为避开飞书消息更新接口限流。
- **群聊只响应 @机器人**：按 `chat_type` + `mentions` 前置过滤，在调 LLM 之前丢弃无关消息，控制推理成本。
- **文件消息自动速读**：下载附件 → 按格式提取文本（PDF / Word / TXT / MD）→ 研报速读。

## 演进方向（Roadmap）

- **L2：Function Calling 路由** —— 把工具注册成 tools，让模型自主判断调用哪个，替代关键词路由（当前版本实测发现关键词覆盖不全，这是真实迭代动因）
- **L3：多步研究 Agent（ReAct）** —— 接 Tavily / Bing 搜索，自主执行「搜 → 读 → 整理 → 出文档」多步流程，补齐行业研究的实时数据
- 接飞书云文档 API：结果一键写入在线 Docx，多人协作编辑
- 多轮对话记忆：按用户记住历史研究主题
