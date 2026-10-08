#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
赛后自动结算 settle.py
=====================
输入比分 → 结算追踪表待结算项；--auto 模式从 football-data.co.uk
拉取最新比分自动结算，并回填收盘赔率（市场平均 Avg 列）算 CLV。

用法：
  python scripts/settle.py --list
  python scripts/settle.py --id 3 --score "2-1" --result 胜
  python scripts/settle.py --auto --pack data/英超_Arsenal_vs_Chelsea.json

注意：收盘赔率取 football-data.co.uk 的 Avg（市场平均）列；
Pinnacle 收盘列 2025-07-23 后系统性滞后，不用。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent
TRACKER_CSV = REPO / "data" / "tracker.csv"
COLUMNS = [
    "id", "date", "league", "match", "pick", "prob", "confidence",
    "stake", "market_odds", "closing_odds", "clv", "result", "score", "settled",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (jingcai-betting-skill; settle)"})

LEAGUE_CODES = {
    "英超": "E0", "西甲": "SP1", "德甲": "D1", "意甲": "I1", "法甲": "F1",
    "英冠": "E1", "荷甲": "N1", "葡超": "P1", "苏超": "SC0",
    "巴甲": "B1", "日职": "J1", "墨超": "MEX", "美职": "MLS", "瑞典超": "S1",
}
FD_BASE = "https://www.football-data.co.uk/mmz4281"


def _read_rows():
    with open(TRACKER_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_list(_args):
    rows = [r for r in _read_rows() if r["settled"] != "yes"]
    if not rows:
        print("[settle] 无待结算单据")
        return
    print(f"{'id':<4}{'日期':<12}{'联赛':<6}{'比赛':<28}{'方向':<12}{'赔率':<7}")
    for r in rows:
        print(f"{r['id']:<4}{r['date']:<12}{r['league']:<6}"
              f"{r['match']:<28}{r['pick']:<12}{r['market_odds']:<7}")


def cmd_manual(args):
    """手动结算：直接输入比分与结果（委托 tracker.py，保证单点写入）。"""
    cmd = [sys.executable, str(REPO / "scripts" / "tracker.py"),
           "settle", "--id", args.id, "--result", args.result,
           "--score", args.score or ""]
    if args.closing_odds:
        cmd += ["--closing-odds", args.closing_odds]
    subprocess.run(cmd, check=True)


def _result_for_pick(pick: str, home_zh: str, away_zh: str,
                     hg: int, ag: int) -> str:
    """根据 pick 文本与比分判定 胜/平/负（相对 pick 方向）。"""
    total = hg + ag
    if "大" in pick:
        if total > 2.5:
            return "胜"
        return "负"
    if "小" in pick:
        if total < 2.5:
            return "胜"
        return "负"
    # 胜平负
    if hg > ag:
        winner = "home"
    elif hg < ag:
        winner = "away"
    else:
        winner = "draw"
    if "平" in pick and "胜" not in pick and "负" not in pick:
        side = "draw"
    elif home_zh in pick or "主胜" in pick:
        side = "home"
    elif away_zh in pick or "客胜" in pick:
        side = "away"
    else:
        return "平"  # 无法判断，保守记平并人工复核
    return "胜" if side == winner else "负"


def _closing_odds_for(row: pd.Series, pick: str,
                      home_zh: str, away_zh: str) -> str:
    """取市场平均收盘赔率（Avg 列），按 pick 方向取对应列。"""
    try:
        if "大" in pick or "小" in pick:
            col = "AvgC>2.5" if "大" in pick else "AvgC<2.5"
            alt = "Avg>2.5" if "大" in pick else "Avg<2.5"
            v = row.get(col)
            if pd.isna(v):
                v = row.get(alt)
        elif home_zh in pick or "主胜" in pick:
            v = row.get("AvgCH")
        elif away_zh in pick or "客胜" in pick:
            v = row.get("AvgCA")
        else:  # 平局方向
            v = row.get("AvgCD")
        return str(v) if pd.notna(v) else ""
    except Exception:
        return ""


def cmd_auto(args):
    """从 football-data.co.uk 拉最新比分，自动结算匹配的待结算单。"""
    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    league, home, away = pack["league"], pack["home"], pack["away"]
    home_zh, away_zh = pack.get("home_zh", home), pack.get("away_zh", away)
    code = LEAGUE_CODES.get(league, league)

    frames = []
    for season in ("2526", "2425"):
        url = f"{FD_BASE}/{season}/{code}.csv"
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            frames.append(pd.read_csv(io.StringIO(r.text)))
        except requests.RequestException as exc:
            print(f"[settle] 拉取 {url} 失败: {exc}", file=sys.stderr)
    if not frames:
        sys.exit(1)
    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    played = df.dropna(subset=["FTHG", "FTAG"])
    m = played[(played["HomeTeam"] == home) & (played["AwayTeam"] == away)]
    if m.empty:
        print(f"[settle] 未找到 {home} vs {away} 的已完赛记录")
        sys.exit(1)
    row = m.sort_values("Date").iloc[-1]
    hg, ag = int(row["FTHG"]), int(row["FTAG"])
    score = f"{hg}-{ag}"
    print(f"[settle] 最新完赛：{home} {score} {away}（{row['Date'].date()}）")

    rows = _read_rows()
    settled_any = False
    for r in rows:
        if r["settled"] == "yes":
            continue
        if r["league"] != league:
            continue
        if home_zh not in r["match"] or away_zh not in r["match"]:
            continue
        result = _result_for_pick(r["pick"], home_zh, away_zh, hg, ag)
        closing = _closing_odds_for(row, r["pick"], home_zh, away_zh)
        r["result"], r["score"], r["settled"] = result, score, "yes"
        if closing:
            r["closing_odds"] = closing
            try:
                mo = float(r["market_odds"]) if r["market_odds"] else None
                co = float(closing)
                r["clv"] = str(round(mo - co, 3)) if mo else ""
            except (ValueError, TypeError):
                pass
        settled_any = True
        print(f"[settle] id={r['id']} {r['pick']} → {result}（{score}）"
              f"{' CLV=' + r['clv'] if r.get('clv') else ''}")

    if not settled_any:
        print("[settle] 没有匹配的待结算单据")
        return
    with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    # 同步 markdown
    subprocess.run([sys.executable, str(REPO / "scripts" / "tracker.py"),
                    "summary"], check=True)
    print("[settle] 追踪表已更新（CLV 已回填）")


def main():
    ap = argparse.ArgumentParser(description="赛后结算追踪表")
    sub = ap.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("list", help="列出待结算单据")
    l.set_defaults(fn=cmd_list)

    m = sub.add_parser("manual", help="手动结算（输入比分）")
    m.add_argument("--id", required=True)
    m.add_argument("--score", required=True, help='比分，如 "2-1"')
    m.add_argument("--result", required=True,
                   choices=["胜", "平", "负", "走水", "取消"])
    m.add_argument("--closing-odds", default="")
    m.set_defaults(fn=cmd_manual)

    a = sub.add_parser("auto", help="自动拉比分结算")
    a.add_argument("--pack", required=True, help="fetch_data.py 输出的 JSON")
    a.set_defaults(fn=cmd_auto)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
