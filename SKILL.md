---
name: jingcai-football-analysis
description: 竞彩足球智能分析一句话触发。用户给出对阵（如"单关分析，桑托斯vs弗拉门戈"）后自动执行：数据采集→Dixon-Coles 建模→多方交叉验证→按七条铁律输出→记入追踪表。覆盖竞彩常开联赛（五大联赛/欧冠/日韩/巴甲美职墨超/国家队）。
---

# Purpose

一句话触发的足彩分析流水线。用户说"单关分析，A vs B"即自动跑完
数据采集 → 建模 → 交叉验证 → 铁律输出 → 追踪记账，
"观望（0 元）"是一等输出。详细联赛手册、赔率术语见 references/（按需读取）。

# Workflow

## Step 0 — 触发前检查清单（必须先过）

1. **开球时间校验**：确认比赛未开赛。已开赛/已结束的比赛必须明示状态，
   不得当未开赛分析。
2. **赔率新鲜度确认**：记录赔率快照时间；赔率超过 6 小时未更新则标注"赔率可能过期"。
3. **首发状态判定**：首发已出 → 成品；首发未出 → 输出必须显性标注"⏳半成品"。
4. 以上任一项缺失 → 允许继续，但输出中必须显性标注缺失项。

## Step 1 — 数据采集（scripts/fetch_data.py）

`python scripts/fetch_data.py <联赛> <主队> <客队>` → `data/<slug>.json`

**联赛分级分支**（覆盖范围详见 references/league-data-manual.md）：

- **A 级 xG 联赛**（英超/西甲/德甲/意甲/法甲/俄超）→ 走 xG 增强分支：
  Understat/FBRef 取 xG，叠加到 Dixon-Coles 先验。
- **B 级数据荒漠联赛**（日职/韩K/巴甲/美职/墨超/芬超等）→ 走比分+Elo+收盘赔率分支：
  无 xG（不要编造）；ClubElo 缺失时 fallback 纯比分拟合。
- **C 级国家队赛事** → 国家队 Elo + 大赛历史，样本小，置信度上限为"中"。

sporttery.cn（竞彩官方）有反爬，不做自动抓取，官方赔率人工核对。

## Step 2 — 建模（scripts/model.py）

`python scripts/model.py --pack data/<slug>.json --book-odds "主,平,客"`

- penaltyblog Dixon-Coles 拟合 → 胜平负/大小球概率
- overround removal 去水 → 市场隐含概率；输出模型 vs 市场 edge
- 极端概率（>80%/<5%）只作风险提示（铁律6）

## Step 3 — 交叉验证（playbooks/crosscheck.md）

5 账号分工 + 权威媒体，只取事实不取结论；分歧按手册裁决（铁律7）。
基本面 55 开 + 赔率降幅 >5% → 资金信号权重最高（铁律3）。

## Step 4 — 输出（playbooks/output_template.md）

主方向与对冲必须标概率权重（铁律1）；显性标注"成品"/"半成品"（铁律2）；
纪律账三行：本注占比/累计盈亏/距 7000 元红线；单注 >1000 元直接拦截。
输出末尾必须附带**固定 JSON 输出块**（字段见 Output Contract），
供 tracker.py 自动解析记账。

## Step 5 — 记账与日志

- `python scripts/tracker.py add-from-json <json>`：解析输出 JSON 记入追踪表，
  自动记录 CLV（投注赔率 vs 收盘市场平均）。
- 每次分析冻结"赔率快照+首发快照+模型版本+数据日期"写入 `predictions/`（JSONL）。
- 赛后：`python scripts/settle.py` 结算 → `python scripts/calibration.py`
  每 50 单输出 Brier 校准报告。

# Output Contract

每次分析输出末尾的 JSON 块（tracker.py 解析用），字段固定：

```json
{
  "match": "桑托斯 vs 弗拉门戈",
  "league": "巴甲",
  "market": "胜平负",
  "pick": "弗拉门戈胜",
  "prob": 0.54,
  "hedge": {"pick": "平", "prob": 0.23},
  "confidence": "中",
  "stake": 0,
  "market_odds": 1.80,
  "odds_snapshot_at": "2026-10-09T00:30:00+08:00",
  "lineup_status": "半成品",
  "analyzed_at": "2026-10-09T00:35:00+08:00",
  "model_version": "penaltyblog-1.13.1/dixon-coles",
  "data_date": "2026-10-09"
}
```

# Operating Rules

1. 七条铁律硬编码进流水线，任何一步不得跳过（全文见 references/iron-rules.md，
   各条已并入对应的 playbook/脚本）。
2. 资金纪律：本金 10000；单注 ≤1000（超限拦截）；单日亏 2000 停手；
   跌破 7000 暂停一周；连黑 3 单降注。
3. 不编造数据：映射缺失原样透传；xG 荒漠联赛不编 xG。
4. 无 key/token：全部免费公开渠道。
5. 免责声明：仅供研究娱乐，不构成投注建议（见 README）。
