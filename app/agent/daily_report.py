"""每日行业日报：cron 调度 + JSON 持久化 + daemon 线程。

使用场景（对应 JD"自动搜集和整理行业信息"）：
    每天早上 9 点自动搜索指定行业主题的最新动态，整理成日报卡片推到飞书群。

- cron 表达式（5 段：分 时 日 月 周）匹配逻辑从原运维 Agent 搬来，未做改动
- 任务持久化到 .agent_data/report_jobs.json，服务重启不丢
- 单 daemon 线程每分钟检查一次；执行体是 ResearchAgent（自动 web_search + 整理）
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.agent.constants import _DATA_DIR
from app.card import markdown_to_card
from app import feishu_client

logger = logging.getLogger("feishu-bot")

_JOBS_PATH = _DATA_DIR / "report_jobs.json"
_jobs: dict[str, "ReportJob"] = {}
_lock = threading.RLock()
_last_fired: dict[str, datetime] = {}
_scheduler_thread: threading.Thread | None = None


@dataclass
class ReportJob:
    id: str
    cron: str          # 5 段 cron 表达式，如 "0 9 * * *" 每天 9 点
    chat_id: str       # 目标飞书群
    topic: str         # 日报主题，如 "人形机器人"
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


# ---------- cron 表达式匹配（搬自原运维 Agent，标准 5 段实现） ----------

def _cron_field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        step = 1
        if "*/" in part:
            step = int(part.split("*/")[1])
            return value % step == 0
        if "/" in part:
            range_part, step_str = part.split("/")
            step = int(step_str)
            if "-" in range_part:
                start, end = map(int, range_part.split("-"))
                if start <= value <= end and (value - start) % step == 0:
                    return True
            else:
                start = int(range_part)
                if value >= start and (value - start) % step == 0:
                    return True
        elif "-" in part:
            start, end = map(int, part.split("-"))
            if start <= value <= end:
                return True
        else:
            if int(part) == value:
                return True
    return False


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    minute, hour, day, month, weekday = parts
    if not _cron_field_matches(minute, dt.minute):
        return False
    if not _cron_field_matches(hour, dt.hour):
        return False
    if not _cron_field_matches(month, dt.month):
        return False
    day_matches = _cron_field_matches(day, dt.day)
    cron_weekday = (dt.weekday() + 1) % 7
    weekday_matches = _cron_field_matches(weekday, cron_weekday)
    if cron_weekday == 0:
        weekday_matches = weekday_matches or _cron_field_matches(weekday, 7)
    if day == "*" or weekday == "*":
        return day_matches and weekday_matches
    return day_matches or weekday_matches


def validate_cron(cron_expr: str) -> bool:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    for field, (lo, hi) in zip(parts, ranges):
        if field == "*":
            continue
        for part in field.split(","):
            try:
                p = part.split("/")[0]
                if "-" in p:
                    a, b = map(int, p.split("-"))
                    if a < lo or b > hi or a > b:
                        return False
                elif p != "*":
                    v = int(p)
                    if v < lo or v > hi:
                        return False
            except ValueError:
                return False
    return True


# ---------- 任务持久化与增删查 ----------

def _save() -> None:
    _JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _JOBS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({jid: asdict(j) for jid, j in _jobs.items()}, f, ensure_ascii=False, indent=1)
    tmp.replace(_JOBS_PATH)


def load_jobs() -> None:
    if not _JOBS_PATH.exists():
        return
    try:
        with open(_JOBS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for jid, jd in data.items():
            _jobs[jid] = ReportJob(**jd)
        logger.info("[daily_report] 加载 %d 个日报任务", len(_jobs))
    except Exception:
        logger.exception("[daily_report] 任务文件损坏，忽略")


def add_job(cron: str, chat_id: str, topic: str) -> ReportJob:
    if not validate_cron(cron):
        raise ValueError(f"非法 cron 表达式: {cron}")
    job = ReportJob(id=f"rpt_{uuid.uuid4().hex[:12]}", cron=cron, chat_id=chat_id, topic=topic)
    with _lock:
        _jobs[job.id] = job
        _save()
    return job


def remove_job(job_id: str) -> bool:
    with _lock:
        if _jobs.pop(job_id, None) is None:
            return False
        _last_fired.pop(job_id, None)
        _save()
        return True


def list_jobs() -> list[dict]:
    with _lock:
        return [asdict(j) for j in _jobs.values()]


# ---------- 执行体：Agent 生成日报 → 发卡片到群 ----------

_REPORT_PROMPT = """今天是 {date}。请为投研团队生成一份「{topic}」行业日报：

1. 先用 web_search 多角度搜索该领域最近的重要动态（政策、融资、产品、技术进展），建议搜 2-4 次，关键词带"最新/2025/2026"等时间词
2. 再整理成一份简洁日报，Markdown 格式：

## 📰 今日要闻
- 3-6 条，每条一句话说清事实，附来源媒体名

## 🔍 值得关注的信号
- 1-3 条你的解读（为什么这事对投资有意义）

## ✅ 建议动作
- 1-2 条投研同事今天可以做的事

全文控制在 600 字以内，适合群里快速阅读；搜不到足够新闻时如实说明，不要编造。"""


def run_job(job: ReportJob) -> None:
    """执行一次日报：Agent 自主搜索整理 → 卡片推到目标群。"""
    from app.agent.agent import ResearchAgent  # 延迟 import 避免循环

    logger.info("[daily_report] 执行 %s topic=%s", job.id, job.topic)
    try:
        agent = ResearchAgent()
        md = agent.run(_REPORT_PROMPT.format(date=datetime.now().strftime("%Y-%m-%d"), topic=job.topic))
        if not md.strip():
            md = f"今日「{job.topic}」日报生成失败：模型未返回内容。"
        feishu_client.send_card(
            job.chat_id,
            markdown_to_card(md, title=f"{job.topic} · 每日行业日报"),
        )
        logger.info("[daily_report] %s 推送完成", job.id)
    except Exception:
        logger.exception("[daily_report] %s 执行失败", job.id)
        try:
            feishu_client.send_card(
                job.chat_id,
                markdown_to_card(f"⚠️ 今日「{job.topic}」日报生成失败，请查看服务日志。", title=f"{job.topic} · 每日行业日报"),
            )
        except Exception:
            logger.exception("[daily_report] %s 失败通知也发送失败", job.id)


def _scheduler_loop() -> None:
    while True:
        now = datetime.now().replace(second=0, microsecond=0)
        with _lock:
            for job in list(_jobs.values()):
                if not job.enabled or not cron_matches(job.cron, now):
                    continue
                last = _last_fired.get(job.id)
                if last is not None and last >= now:
                    continue
                _last_fired[job.id] = now
                # 单独线程执行，不阻塞调度循环（日报生成要 1-2 分钟）
                threading.Thread(target=run_job, args=(job,), daemon=True).start()
        time.sleep(30)


def start_scheduler() -> None:
    """服务启动时调用：加载任务并启动调度线程（幂等）。"""
    global _scheduler_thread
    with _lock:
        load_jobs()
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop, daemon=True, name="daily-report-scheduler"
        )
        _scheduler_thread.start()
        logger.info("[daily_report] 调度线程已启动")
