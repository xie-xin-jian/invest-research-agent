# 飞书一句话投研 Bot

> 在飞书群里 `@机器人` + 一句话，自动产出结构化投研内容。
> 由 DeepSeek 驱动。

覆盖招聘 JD 的三类职责：

| 一句话指令 | 输出 |
|---|---|
| `@bot 研究下人形机器人行业` | 行业概览 / 头部玩家 / 关键数据 / 风险 / 建议关注 |
| `@bot 读研报：[粘贴研报文本]` | 核心结论 / 关键数据 / 风险提示 / 适合谁看 |
| `@bot 纪要：[粘贴纪要原文]` | 议题决议 / 行动项 / 待跟进 |

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
│   ├── main.py             # FastAPI 入口 + 飞书 webhook
│   ├── feishu_client.py    # 飞书消息收发（token / 回复 / 卡片）
│   ├── card.py             # Markdown → 飞书交互卡片
│   ├── llm.py              # DeepSeek 调用封装
│   ├── router.py           # 关键词路由 → 三个工具
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

## 扩展方向（如果有时间）

- 接 Tavily / Bing 搜索增强行业研究的实时性
- 接飞书云文档 API：把研报速读结果一键写入飞书 Docx
- 接飞书文件下载：用户发研报附件，机器人自动下载、提取文本、跑速读
- 加流式更新卡片（DeepSeek `chat_stream` + 飞书 `update_card`）
