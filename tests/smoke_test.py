"""端到端冒烟测试：不依赖飞书回调，直接验证三个工具 + 路由器 + 卡片渲染。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools import industry_research, report_reader, meeting_notes
from app.router import route
from app.card import markdown_to_card


def banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_industry() -> None:
    banner("场景1: 行业研究")
    t0 = time.time()
    md = industry_research.research("人形机器人")
    print(f"[耗时 {time.time()-t0:.1f}s] 输出 {len(md)} 字符")
    print("--- 前 600 字 ---")
    print(md[:600])
    assert "## 一" in md or "## 二" in md, "行业简报缺小节"
    print("✓ 行业研究 OK")


def test_report() -> None:
    banner("场景2: 研报速读")
    sample = """2024年中国人形机器人行业迎来爆发期。根据高盛预测,2030年全球人形机器人市场规模将达
到380亿美元,CAGR约76%。国内代表企业包括优必选(UBTECH)、宇树科技(Unitree)、智元机器人
(Agibot)等。优必选Walker S系列已在比亚迪工厂进行装配实训,单台售价约23.8万美元。宇树H1
G1型号定价9.9万元人民币,主打性价比。技术路线上,特斯拉Optimus Gen 2采用纯视觉方案,
国内厂商多采用视觉+力矩传感混合方案。风险包括:核心零部件(谐波减速器、伺服电机)国产化
率仍低,量产爬坡可能不及预期,B端商业化场景验证不足。建议关注具备整机集成能力+核心零部件
自研能力的厂商,以及汽车主机厂背景的集成商。"""
    t0 = time.time()
    md = report_reader.read(sample)
    print(f"[耗时 {time.time()-t0:.1f}s] 输出 {len(md)} 字符")
    print("--- 前 600 字 ---")
    print(md[:600])
    assert "## " in md, "研报摘要缺小节"
    print("✓ 研报速读 OK")


def test_meeting() -> None:
    banner("场景3: 会议纪要结构化")
    sample = """今天会议主要讨论人形机器人赛道投资策略。张总先讲了,他认为特斯拉Optimus进度超
预期,建议重点关注产业链上游。李总补充,国内优必选和宇树技术路线更接地气,而且宇树G1
9.9万的定价很有杀伤力。王总提出担心,核心零部件国产化率太低,谐波减速器还是依赖日本
哈默纳科。最后决议:这周张总负责拉通优必选IR会议,李总跟进宇树最新一轮估值,下周三
再碰一次。"""
    t0 = time.time()
    md = meeting_notes.structure(sample)
    print(f"[耗时 {time.time()-t0:.1f}s] 输出 {len(md)} 字符")
    print("--- 前 600 字 ---")
    print(md[:600])
    assert "## " in md, "纪要缺小节"
    print("✓ 会议纪要 OK")


def test_router() -> None:
    banner("路由器: 关键词分流")
    # 只检查关键词 prefix 处理，不实际调用 LLM
    from app.router import _strip_prefix
    assert _strip_prefix("研究人形机器人", ("研究", "调研")) == "人形机器人"
    assert _strip_prefix("读研报：xxx", ("读研报",)) == "xxx" or _strip_prefix("读研报:xxx", ("读研报",)) == "xxx"
    print("✓ 路由器 prefix 处理 OK")


def test_card() -> None:
    banner("卡片渲染")
    card = markdown_to_card("# 测试标题\n\n- 项目A\n- 项目B", title="投研助理")
    print(json.dumps(card, ensure_ascii=False, indent=2))
    assert card["header"]["template"] == "green"
    assert any(e["tag"] == "markdown" for e in card["elements"])
    print("✓ 卡片结构 OK")


def test_webhook_local() -> None:
    banner("webhook 路由(本地 HTTP)")
    import httpx
    # challenge
    r = httpx.post("http://localhost:8000/feishu/webhook",
                   json={"type": "url_verification", "challenge": "abc123"},
                   timeout=10)
    print("challenge:", r.status_code, r.json())
    assert r.json().get("challenge") == "abc123"
    print("✓ webhook challenge OK")


if __name__ == "__main__":
    test_router()
    test_card()
    test_webhook_local()
    test_industry()
    test_report()
    test_meeting()
    banner("全部冒烟测试通过")
