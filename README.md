# 飞书一句话投研 Bot

> 在飞书群里 `@机器人` + 一句话，AI Agent 自己判断该搜索、读文档还是整理纪要，自动产出结构化投研内容。
> 由 DeepSeek 驱动（Anthropic 兼容端点 + Function Calling）。

| 一句话输入 | Agent 行为 | 输出 |
|---|---|---|
| `@bot 研究下人形机器人行业` | 自动调 `industry_research` + 多轮 `web_search` 补实时数据 | 行业概览 / 头部玩家 / 关键数据 / 风险 / 建议关注 |
| `@bot 最近固态电池有什么新动态` | 自动多轮 `web_search`（政策/融资/技术多角度） | 带来源的最新动态整理 |
| `@bot 读研报：[粘贴文本]` 或直接发文件 | 自动调 `report_reader` | 核心结论 / 关键数据 / 风险提示 |
| `@bot [直接粘贴会议记录]` | 自动识别材料性质，调 `meeting_notes` | 议题决议 / 行动项 / 待跟进 |
| `@bot 出文档：某行业资料整理` | 生成资料 → 转 Word → 发回群聊 | 可下载的 Word 文档 |
| 闲聊/自由提问 | 判断无需工具，直接回答 | 自然对话 |

无需记任何固定指令——模型通过 Function Calling 自主选择工具。

## 架构

```
飞书事件订阅 ──► FastAPI webhook（3s 内 200 / event_id 幂等 / 群聊@过滤）
                      │ BackgroundTasks
                      ▼
                ResearchAgent 循环（pipeline）
                  ┌─ 会话缓存恢复（同用户 30 分钟内对话历史，支持上下文指代）
                  ├─ 调 DeepSeek（Anthropic 端点，带 tools）
                  │     │ 模型返回 tool_use
                  │     ▼
                  │   ToolRegistry ─► ToolExecutor ─► 工具执行
                  │     │              ├─ web_search       联网搜索（DuckDuckGo）
                  │     │              ├─ industry_research 行业简报
                  │     │              ├─ report_reader     研报速读
                  │     │              └─ meeting_notes     纪要结构化
                  │     │ 结果回喂模型，进入下一轮（上限 12 轮）
                  │     ▼ 模型输出纯文本
                  └─ 事件流 ─► 飞书卡片 1s 节流更新（逐字效果）
                        └─ 会话保存（供下次同用户提问时恢复上下文）

日报调度（daemon 线程）──► cron 匹配 ─► ResearchAgent 生成日报 ─► 推送指定群
```

## 目录结构

```
feishu-research-bot/
├── app/
│   ├── main.py             # FastAPI 入口 + 飞书 webhook + 日报管理 API
│   ├── feishu_client.py    # 飞书 API 封装（token / 回复 / 卡片 / 主动发群 / 文件）
│   ├── card.py             # Markdown → 飞书交互卡片
│   ├── llm.py              # DeepSeek OpenAI 兼容调用（工具内部模板用）
│   ├── docx_export.py      # Markdown → Word 文档
│   ├── agent/              # Agent 核心（Function Calling 循环）
│   │   ├── agent.py        # ResearchAgent：组装 client + 工具 + 会话缓存
│   │   ├── pipeline.py     # 推理主循环：调模型 → 执行 tool_use → 回喂 → 直到纯文本
│   │   ├── tool_loop.py    # API 调用 + tool_use/tool_result 配对修复
│   │   ├── tools.py        # ToolRegistry（schema+handler）+ ToolExecutor（异常回喂模型）
│   │   ├── tool_specs.py   # 四个投研工具的 schema 注册
│   │   ├── context_manager.py  # system prompt（身份/工具说明/工作方式）
│   │   ├── context_compact.py  # 上下文压缩：大结果落盘 / 旧结果占位 / 模型摘要 / 中间裁剪
│   │   ├── error_recovery.py   # 429 指数退避 / 上下文超长恢复 / 输出 token 扩容
│   │   └── daily_report.py # 每日行业日报：cron 调度 + 任务持久化
│   └── tools/
│       ├── web_search.py        # 联网搜索（DuckDuckGo，免 key）
│       ├── industry_research.py # 行业简报
│       ├── report_reader.py     # 研报速读
│       └── meeting_notes.py     # 会议纪要结构化
├── config.py               # 配置加载（.env）
├── requirements.txt
├── .env.example
└── README.md
```

## 本地调试

### 1. 准备凭证

**飞书自建应用**（[open.feishu.cn/app](https://open.feishu.cn/app)）：
- 创建企业自建应用，记下 `App ID` / `App Secret`
- 权限管理 → 开通：`im:message`、`im:message.group_at_msg`、`im:message.p2p_msg`（接收消息）、`im:message:send_as_bot`（发送消息）、`im:resource`（文件上传，出文档功能需要）
- 事件订阅 → 添加事件：`im.message.receive_v1`
- 记下 `Verification Token`（事件订阅页）

**DeepSeek API**（[platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)）：
- 创建 API Key

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入上面的凭证
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. 内网穿透

飞书 webhook 需要公网可达。本地调试用隧道把 localhost 暴露出去：

```bash
# 方式一：ngrok
ngrok http 8000
# 把生成的 https://xxx.ngrok-free.app/feishu/webhook 填回飞书事件订阅

# 方式二：cloudflared
cloudflared tunnel --url http://localhost:8000
```

### 6. 验证

在飞书群里 `@机器人` 发一句话（如"研究下人形机器人行业"），看到卡片逐字更新即为成功。

## 实际使用

### 日常使用

在飞书群或私聊中直接对话机器人：

| 场景 | 输入示例 |
|---|---|
| 行业研究 | `@bot 研究下低空经济` |
| 联网搜最新动态 | `@bot 最近固态电池有什么新动态` |
| 研报速读 | `@bot 读研报：[粘贴文本]` 或直接发 PDF/Word/TXT 文件 |
| 会议纪要 | `@bot [直接粘贴会议记录]`（不需要加前缀） |
| 生成 Word 文档 | `@bot 出文档：人形机器人行业资料整理` |
| 闲聊/自由提问 | `@bot 私募股权和创投有什么区别` |
| 上下文追问 | 先问"研究下人形机器人"，等回复后再问"这个赛道的上游呢"（30 分钟内有效） |

### 每日行业日报（可选）

通过 HTTP API 配置定时推送（任务持久化，重启不丢）：

```bash
# 每天早上 9 点，向指定群推送"人形机器人"行业日报
curl -X POST http://localhost:8000/reports/jobs \
  -H "Content-Type: application/json" \
  -d '{"cron": "0 9 * * *", "chat_id": "oc_xxx群ID", "topic": "人形机器人"}'

# 查看 / 删除 / 手动触发一次（测试）
curl http://localhost:8000/reports/jobs
curl -X DELETE http://localhost:8000/reports/jobs/<job_id>
curl -X POST http://localhost:8000/reports/jobs/<job_id>/run
```

> cron 时区为 `Asia/Shanghai`。`chat_id` 可从飞书事件日志的 `payload.event.message.chat_id` 获取（在群里 @ 一次机器人看日志即可拿到）。

### 生产部署

```bash
# 用 nohup 后台运行
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 或用 systemd 管理进程
```

## 设计取舍

- **DeepSeek Anthropic 兼容端点**：Anthropic SDK 的 tool-use block 协议成熟，DeepSeek 提供兼容端点后可零改动复用 Agent 循环基建，成本低。
- **Function Calling 路由替代关键词路由**：关键词覆盖不全（用户不会按说明书说话），模型看 schema description 自己选工具，实测无前缀粘贴纪要也能正确识别。
- **非流式 API + 伪流式切片**：tool_use 场景流式协议处理复杂，改为非流式拿完整响应后按 40 字切片逐段推送，配合 1s 节流，视觉上是逐字效果且实现可靠。
- **工具异常回喂模型**：ToolExecutor 把异常兜成 `Error: ...` 字符串作为 tool_result 返回，模型看到错误可自我纠正（换关键词重搜等），而不是整条链路崩掉。
- **上下文三级压缩**：大工具结果落盘只留预览 → 旧结果替换占位符 → 模型摘要早期对话，多轮搜索也不怕撑爆 context。
- **会话缓存替代长期记忆**：投研场景每次任务相对独立，长期记忆库会注入噪音干扰模型判断；改用 30 条消息 / 30 分钟过期的会话缓存，满足"第一条吧"这类上下文指代需求，不引入噪音。

## 工程细节

- **webhook 立即 200 + 后台处理**：飞书要求 3 秒内响应否则重推；配合 `event_id` 幂等去重（5 分钟窗口），一条消息只处理一次。
- **1s 节流更新卡片**：避开飞书消息更新接口限流（429）。
- **群聊只响应 @机器人**：按 `chat_type` + `mentions` 前置过滤，在调 LLM 之前丢弃无关消息，控制推理成本。
- **@ 占位符全文清理**：飞书消息 text 里 `@_user_1` 占位符可能出现在开头/中间/末尾，按 mention key 全文替换清理，模型不会收到乱码文本。
- **tool_use/tool_result 配对修复**：上轮中断可能留下没有 result 的 tool_use，每次调 API 前扫描修复，避免 400。
- **会话缓存**：按 `user:{open_id}` 隔离，30 条消息上限 / 30 分钟 TTL 自动过期，模型能理解"第一条吧"这类上下文指代。
- **日报调度**：daemon 线程 30s 粒度检查 cron 表达式，任务 JSON 持久化，执行单独起线程不阻塞调度。

## 演进记录

- **L1（已完成）**：关键词路由 + 三个固定工具 + 流式卡片
- **L2（已完成）**：Function Calling 路由替代关键词路由，新增 web_search 工具，模型自主多轮「搜→读→整理」
- **L3（已完成）**：会话缓存支持多轮上下文指代 + 每日行业日报定时推送
- **下一步**：接飞书云文档 API 一键写入在线 Docx；搜索结果按域名可信度加权；日报支持多主题合并推送
