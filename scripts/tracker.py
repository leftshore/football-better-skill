#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
追踪表 tracker.py
=================
铁律5：每次推荐记入置信度-结果追踪表，长期校准"高/中/低"对应的真实胜率。
铁律4：用过程质量而非单场结果评价决策。

用法：
  python scripts/tracker.py add --match "桑托斯vs弗拉门戈" --league 巴甲 \\
      --pick 弗拉门戈胜 --prob 0.54 --confidence 中 --stake 0 --market-odds 1.80
  python scripts/tracker.py settle --id 3 --result 平 --score "1-1"
  python scripts/tracker.py summary

赛后结算：--result 取值 胜/平/负/走水/取消（相对 pick 方向）。
CLV 记录：--clv 填 (投注价 - 收盘价) 的差值，正值=正 CLV（金标准）。
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

TRACKER_CSV = Path(__file__).resolve().parent.parent / "data" / "tracker.csv"
TRACKER_MD = Path(__file__).resolve().parent.parent / "data" / "tracker.md"

COLUMNS = [
    "id", "date", "league", "match", "pick", "prob", "confidence",
    "stake", "market_odds", "closing_odds", "clv", "result", "score", "settled",
]

# CLV（收盘赔率价值）= 投注时赔率 − 收盘赔率，正值 = 拿到比收盘更好的价格。
# 收盘价来源：football-data.co.uk 的市场平均（Avg）收盘列。
# 注意：其 Pinnacle 收盘列 2025-07-23 后系统性滞后，不用 Pinnacle 列算 CLV。

BANKROLL = 10000.0   # 本金
STOP_LINE = 7000.0   # 红线
SINGLE_MAX = 1000.0  # 单注上限
DAILY_STOP = 2000.0  # 单日止损


def _ensure_csv():
    TRACKER_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not TRACKER_CSV.exists():
        with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writeheader()


def _read_rows():
    _ensure_csv()
    with open(TRACKER_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(rows):
    with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def _calc_clv(market_odds: str, closing_odds: str) -> str:
    """CLV = 投注赔率 − 收盘赔率；任一缺失返回空。"""
    try:
        if not market_odds or not closing_odds:
            return ""
        return str(round(float(market_odds) - float(closing_odds), 3))
    except (ValueError, TypeError):
        return ""


def _append_row(rows, *, league="", match, pick, prob, confidence,
                stake, market_odds="", closing_odds=""):
    if float(stake) > SINGLE_MAX:
        print(f"[tracker] 拦截：单注 {stake} 超过上限 {SINGLE_MAX} 元", file=sys.stderr)
        sys.exit(2)
    new_id = str(max([int(r["id"]) for r in rows], default=0) + 1)
    rows.append({
        "id": new_id, "date": date.today().isoformat(),
        "league": league, "match": match, "pick": pick,
        "prob": prob, "confidence": confidence,
        "stake": stake, "market_odds": market_odds,
        "closing_odds": closing_odds,
        "clv": _calc_clv(market_odds, closing_odds),
        "result": "", "score": "", "settled": "no",
    })
    return new_id


def cmd_add(args):
    rows = _read_rows()
    new_id = _append_row(
        rows, league=args.league, match=args.match, pick=args.pick,
        prob=args.prob, confidence=args.confidence, stake=args.stake,
        market_odds=args.market_odds or "",
        closing_odds=args.closing_odds or "",
    )
    _write_rows(rows)
    render_md(rows)
    print(f"[tracker] 已记入第 {new_id} 单：{args.match} → {args.pick}（{args.confidence}）")


def cmd_add_from_json(args):
    """解析分析输出的固定 JSON 块，自动记入追踪表。"""
    import json as _json
    text = Path(args.json).read_text(encoding="utf-8")
    # 容忍 JSON 块前后有多余文字：取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        print("[tracker] JSON 解析失败：未找到 JSON 块", file=sys.stderr)
        sys.exit(1)
    d = _json.loads(text[start:end + 1])
    hedge = d.get("hedge") or {}
    rows = _read_rows()
    new_id = _append_row(
        rows,
        league=d.get("league", ""), match=d.get("match", ""),
        pick=d.get("pick", ""), prob=d.get("prob", ""),
        confidence=d.get("confidence", "中"), stake=d.get("stake", 0),
        market_odds=str(d.get("market_odds") or ""),
        closing_odds=str(d.get("closing_odds") or ""),
    )
    # 首发状态 / 对冲信息写入备注行
    rows[-1]["match"] = f"{d.get('match','')} [{d.get('lineup_status','')}]"
    _write_rows(rows)
    render_md(rows)
    print(f"[tracker] 已从 JSON 记入第 {new_id} 单：{d.get('match')} → {d.get('pick')}"
          f"（对冲：{hedge.get('pick')}{hedge.get('prob')}）")


def cmd_settle(args):
    rows = _read_rows()
    hit = False
    for r in rows:
        if r["id"] == args.id:
            r["result"] = args.result
            r["score"] = args.score or ""
            if args.closing_odds:
                r["closing_odds"] = args.closing_odds
                r["clv"] = _calc_clv(r.get("market_odds", ""), args.closing_odds)
            r["settled"] = "yes"
            hit = True
    if not hit:
        print(f"[tracker] 未找到 id={args.id}", file=sys.stderr)
        sys.exit(1)
    _write_rows(rows)
    render_md(rows)
    print(f"[tracker] 第 {args.id} 单已结算：{args.result}")


def pnl_of(r) -> float:
    """按欧洲赔率结算单场盈亏（stake=0 时返回 0）。"""
    try:
        stake = float(r["stake"] or 0)
        odds = float(r["market_odds"] or 0)
    except ValueError:
        return 0.0
    if r["settled"] != "yes" or stake <= 0:
        return 0.0
    if r["result"] == "胜":
        return round(stake * (odds - 1), 2)
    if r["result"] in ("平", "负"):
        return round(-stake, 2)
    return 0.0  # 走水/取消


def cmd_clv(_args):
    """CLV 汇总统计：正 CLV 占比、均值——过程质量的金标准。"""
    rows = _read_rows()
    clvs = []
    for r in rows:
        try:
            if r.get("clv"):
                clvs.append(float(r["clv"]))
        except (ValueError, TypeError):
            pass
    n = len(clvs)
    print("===== CLV 汇总（铁律4：过程质量）=====")
    print(f"已记录 CLV：{n} 单")
    if not n:
        print("暂无数据：赛后用 settle --closing-odds 回填收盘赔率")
        return
    pos = sum(1 for c in clvs if c > 0)
    print(f"正 CLV：{pos}/{n}（{pos / n * 100:.0f}%）")
    print(f"平均 CLV：{sum(clvs) / n:+.3f}")
    print(f"中位 CLV：{sorted(clvs)[n // 2]:+.3f}")
    if pos / n >= 0.6:
        print("结论：持续正 CLV，过程质量健康（比盈亏更早显现 edge）")
    elif pos / n <= 0.4:
        print("结论：CLV 偏弱，检查是否在追高水位/过期赔率下单")


def cmd_summary(_args):
    rows = _read_rows()
    settled = [r for r in rows if r["settled"] == "yes"]
    total_pnl = round(sum(pnl_of(r) for r in settled), 2)
    bankroll = round(BANKROLL + total_pnl, 2)
    today = date.today().isoformat()
    today_loss = -sum(pnl_of(r) for r in settled
                      if r["date"] == today and pnl_of(r) < 0)
    consec_black = 0
    for r in reversed(settled):
        if r["result"] in ("平", "负"):
            consec_black += 1
        else:
            break
    conf_stats = {}
    for r in settled:
        c = r["confidence"] or "未标"
        s = conf_stats.setdefault(c, {"n": 0, "hit": 0})
        s["n"] += 1
        if r["result"] == "胜":
            s["hit"] += 1
    print("===== 纪律账 =====")
    print(f"本金：{BANKROLL:.0f} 元 ｜ 累计盈亏：{total_pnl:+.0f} 元")
    print(f"当前本金：{bankroll:.0f} 元 ｜ 距 7000 元红线：{bankroll - STOP_LINE:.0f} 元")
    print(f"今日亏损：{today_loss:.0f} 元（单日亏 2000 停手）")
    print(f"连黑：{consec_black} 单（3 单降注）")
    if bankroll < STOP_LINE:
        print("⚠️ 本金跌破 7000 元红线：暂停一周复盘")
    print("===== 置信度校准（铁律5）=====")
    for c, s in conf_stats.items():
        rate = s["hit"] / s["n"] * 100 if s["n"] else 0
        print(f"  {c}：{s['n']} 单，命中 {rate:.0f}%")
    render_md(rows)


def render_md(rows):
    """同步生成人类可读的 Markdown 追踪表。"""
    lines = ["# 置信度-结果追踪表", "",
             "> 铁律5：每次推荐记入，长期校准高/中/低对应的真实胜率。", "",
             "| # | 日期 | 联赛 | 比赛 | 方向 | 概率 | 置信度 | 注额 | 市场赔率 | CLV | 结果 | 比分 |",
             "|---|------|------|------|------|------|--------|------|----------|-----|------|------|"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in COLUMNS) + " |")
    TRACKER_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="足彩置信度-结果追踪表")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="记入一单")
    a.add_argument("--match", required=True)
    a.add_argument("--league", default="")
    a.add_argument("--pick", required=True)
    a.add_argument("--prob", required=True)
    a.add_argument("--confidence", required=True, choices=["高", "中", "低"])
    a.add_argument("--stake", required=True)
    a.add_argument("--market-odds", default="")
    a.add_argument("--closing-odds", default="",
                   help="收盘赔率（市场平均 Avg 列；Pinnacle 列 2025-07 后滞后不用）")
    a.set_defaults(fn=cmd_add)

    aj = sub.add_parser("add-from-json", help="解析分析输出 JSON 块自动记入")
    aj.add_argument("json", help="含固定 JSON 输出块的文件路径")
    aj.set_defaults(fn=cmd_add_from_json)

    s = sub.add_parser("settle", help="赛后结算")
    s.add_argument("--id", required=True)
    s.add_argument("--result", required=True, choices=["胜", "平", "负", "走水", "取消"])
    s.add_argument("--score", default="")
    s.add_argument("--closing-odds", default="",
                   help="收盘赔率（市场平均），回填后自动计算 CLV")
    s.set_defaults(fn=cmd_settle)

    sm = sub.add_parser("summary", help="纪律账 + 置信度校准")
    sm.set_defaults(fn=cmd_summary)

    cv = sub.add_parser("clv", help="CLV 汇总统计")
    cv.set_defaults(fn=cmd_clv)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
