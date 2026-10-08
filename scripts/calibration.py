#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准报告 calibration.py
=======================
铁律5：长期校准"高/中/低"置信度对应的真实胜率。
铁律4：用过程质量而非单场结果评价——Brier 评分是概率校准的金标准。

Brier = mean((预测概率 − 实际结果)²)，越小越好；
瞎猜 50% ≈ 0.25，完美预测 = 0。

用法：
  python scripts/calibration.py            # 最近 50 单
  python scripts/calibration.py --n 100    # 最近 100 单
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

TRACKER_CSV = Path(__file__).resolve().parent.parent / "data" / "tracker.csv"


def main():
    ap = argparse.ArgumentParser(description="Brier 评分 + 置信度校准报告")
    ap.add_argument("--n", type=int, default=50, help="统计最近 N 单（默认 50）")
    args = ap.parse_args()

    if not TRACKER_CSV.exists():
        print("[calibration] 追踪表不存在，先跑 tracker.py add", )
        return
    with open(TRACKER_CSV, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["settled"] == "yes"]

    rows = rows[-args.n:]
    if not rows:
        print("[calibration] 暂无已结算单据")
        return

    print(f"===== 校准报告（最近 {len(rows)} 单）=====")
    print(f"{'置信度':<6}{'单数':<6}{'命中率':<8}{'平均标称概率':<12}{'Brier':<8}")
    all_brier, all_n = 0.0, 0
    for conf in ["高", "中", "低"]:
        grp = []
        for r in rows:
            try:
                prob = float(r["prob"])
            except (ValueError, TypeError):
                continue
            if (r["confidence"] or "未标") == conf:
                grp.append((prob, 1.0 if r["result"] == "胜" else 0.0))
        if not grp:
            print(f"{conf:<6}{'0':<6}{'-':<8}{'-':<12}{'-':<8}")
            continue
        n = len(grp)
        hit_rate = sum(o for _, o in grp) / n
        avg_prob = sum(p for p, _ in grp) / n
        brier = sum((p - o) ** 2 for p, o in grp) / n
        all_brier += brier * n
        all_n += n
        flag = ""
        if abs(hit_rate - avg_prob) > 0.15:
            flag = "  ⚠️ 标称与实际偏离>15%，置信度标尺需重调"
        print(f"{conf:<6}{n:<6}{hit_rate:<8.0%}{avg_prob:<12.0%}{brier:<8.4f}{flag}")

    if all_n:
        print(f"\n总体 Brier：{all_brier / all_n:.4f}（参考：瞎猜≈0.25，越小越好）")
    print("\n解读：某档'平均标称概率'应接近其'命中率'；"
          "长期偏离说明该档置信度标高了或标低了，按铁律5 调整。")


if __name__ == "__main__":
    main()
