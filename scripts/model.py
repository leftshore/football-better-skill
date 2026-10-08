#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建模层 model.py
===============
用 penaltyblog 的 Dixon-Coles 模型拟合历史比分，输出胜平负/大小球概率；
用 penaltyblog.implied 做 overround removal（去水），得到市场隐含概率；
输出模型概率 vs 市场概率 + edge。

铁律6：极端模型概率（>80% 或 <5%）只作风险提示，不作锚点。

用法：
  python scripts/model.py --pack data/英超_Arsenal_vs_Chelsea.json
  python scripts/model.py --pack data/xxx.json --book-odds "2.10,3.40,3.60" --total-odds "1.95,1.85"

--book-odds：庄家胜平负赔率（主胜,平,客胜），缺失则跳过去水对比
--total-odds：大小球2.5赔率（大,小），缺失则跳过
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from penaltyblog.implied import calculate_implied
from penaltyblog.models import DixonColesGoalModel

# 铁律6 阈值：超出则只作风险提示
EXTREME_HIGH = 0.80
EXTREME_LOW = 0.05
# edge 阈值：模型概率 - 市场隐含概率 > 5% 才算候选机会
EDGE_THRESHOLD = 0.05


def fit_dixon_coles(history: list[dict]) -> DixonColesGoalModel:
    """用全部历史比赛拟合 Dixon-Coles（近期比赛加权更高）。"""
    df = pd.DataFrame(history)
    df = df.dropna(subset=["FTHG", "FTAG"])
    df = df.sort_values("Date")
    n = len(df)
    if n < 20:
        print(f"[model] 警告：历史样本仅 {n} 场，模型不稳定", file=sys.stderr)
    # 时间衰减权重：越近权重越高
    weights = np.exp(np.linspace(-2.5, 0, n))
    model = DixonColesGoalModel(
        goals_home=df["FTHG"].astype(int).tolist(),
        goals_away=df["FTAG"].astype(int).tolist(),
        teams_home=df["HomeTeam"].tolist(),
        teams_away=df["AwayTeam"].tolist(),
        weights=weights,
    )
    model.fit()
    return model


def devig(odds: list[float], names: list[str]) -> dict:
    """去水：multiplicative 方法算市场隐含概率 + 水位。"""
    res = calculate_implied(odds, market_names=names)
    return {
        "probabilities": dict(zip(names, [round(p, 4) for p in res.probabilities])),
        "margin": round(res.margin, 4),
    }


def extreme_flags(probs: dict[str, float]) -> list[str]:
    """铁律6：标记极端概率。"""
    flags = []
    for k, v in probs.items():
        if v >= EXTREME_HIGH:
            flags.append(f"{k}={v:.0%} 过高，仅作风险提示，不作锚点")
        elif v <= EXTREME_LOW:
            flags.append(f"{k}={v:.0%} 过低，仅作风险提示，不作锚点")
    return flags


def analyze(pack: dict, book_odds: list[float] | None,
            total_odds: list[float] | None) -> dict:
    home, away = pack["home"], pack["away"]
    model = fit_dixon_coles(pack["full_history"])
    grid = model.predict(home, away)

    hw, dr, aw = grid.home_draw_away
    model_1x2 = {
        "home_win": round(float(hw), 4),
        "draw": round(float(dr), 4),
        "away_win": round(float(aw), 4),
    }
    model_totals = {
        "over_2.5": round(float(grid.total_goals("over", 2.5)), 4),
        "under_2.5": round(float(grid.total_goals("under", 2.5)), 4),
    }

    out: dict = {
        "match": f"{pack['home_zh']} vs {pack['away_zh']}",
        "league": pack["league"],
        "n_fitted": len(pack["full_history"]),
        "model_1x2": model_1x2,
        "model_totals_2.5": model_totals,
        "extreme_flags": extreme_flags({**model_1x2, **model_totals}),
    }

    # 市场去水对比
    if book_odds and len(book_odds) == 3:
        mkt = devig(book_odds, ["home_win", "draw", "away_win"])
        edge = {k: round(model_1x2[k] - mkt["probabilities"][k], 4)
                for k in model_1x2}
        out["market_1x2"] = mkt
        out["edge_1x2"] = edge
        out["edge_candidates"] = [
            k for k, v in edge.items() if v >= EDGE_THRESHOLD
        ]
    if total_odds and len(total_odds) == 2:
        mkt = devig(total_odds, ["over_2.5", "under_2.5"])
        edge = {k: round(model_totals[k] - mkt["probabilities"][k], 4)
                for k in model_totals}
        out["market_totals_2.5"] = mkt
        out["edge_totals_2.5"] = edge

    return out


def log_prediction(result: dict, pack: dict, book, totals,
                   lineup_status: str, odds_snapshot_at: str):
    """
    版本化预测日志（防事后修改）：
    把"赔率快照 + 首发快照 + 模型版本 + 数据日期"冻结存入 predictions/predictions.jsonl。
    """
    import penaltyblog
    from datetime import datetime, timezone, timedelta
    pred_dir = Path(__file__).resolve().parent.parent / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    log_file = pred_dir / "predictions.jsonl"
    entry = {
        "analyzed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "model_version": f"penaltyblog-{penaltyblog.__version__}/dixon-coles",
        "data_date": pack.get("fetched_at"),
        "match": result["match"],
        "league": result["league"],
        "lineup_snapshot": lineup_status,
        "odds_snapshot": {
            "at": odds_snapshot_at,
            "book_1x2": book,
            "book_totals_2.5": totals,
        },
        "result": result,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[model] 预测日志已冻结 → {log_file}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Dixon-Coles 建模 + 去水 + edge")
    ap.add_argument("--pack", required=True, help="fetch_data.py 输出的 JSON")
    ap.add_argument("--book-odds", default="",
                    help="庄家胜平负赔率，如 2.10,3.40,3.60")
    ap.add_argument("--total-odds", default="",
                    help="大小球2.5赔率（大,小），如 1.95,1.85")
    ap.add_argument("--lineup", default="未出", choices=["已出", "未出"],
                    help="首发状态：已出=成品，未出=半成品")
    ap.add_argument("--odds-at", default="",
                    help="赔率快照时间，如 2026-10-09T00:30:00+08:00")
    ap.add_argument("--no-log", action="store_true", help="不写版本化预测日志")
    args = ap.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    book = [float(x) for x in args.book_odds.split(",")] if args.book_odds else None
    totals = [float(x) for x in args.total_odds.split(",")] if args.total_odds else None

    result = analyze(pack, book, totals)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.no_log:
        log_prediction(result, pack, book, totals, args.lineup, args.odds_at)


if __name__ == "__main__":
    main()
