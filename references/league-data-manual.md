# 联赛数据手册（references/ 渐进披露）

竞彩常开售联赛：英超、西甲、德甲、意甲、法甲、欧冠、欧联、日职联、韩K联、
巴甲、美职联、墨超、世界杯/欧洲杯/欧国联等国家队赛事；
偶开：荷甲、葡超、英冠、苏超、澳超、瑞典超。

## 联赛分级（决定建模分支）

### A 级：xG 联赛（走 xG 增强分支）
- 英超、西甲、德甲、意甲、法甲、俄超
- xG 来源：Understat（射门级 xG，2014/15 起）、FBRef（球队/球员聚合 xG）
- 采集方式：`scripts/fetch_data.py` 的 `fetch_xg()`（soccerdata.Understat 后端）

### B 级：数据荒漠联赛（走比分+Elo+收盘赔率分支）
- 日职、韩K、巴甲、美职、墨超、芬超等
- **无 xG 数据**：Understat/FBRef 均不覆盖——不要编造 xG
- 建模只用：历史比分（Dixon-Coles）+ ClubElo + 去水后收盘赔率
- ClubElo 南美/日韩覆盖弱或缺失 → fallback 纯比分拟合

### C 级：国家队赛事（世界杯/欧洲杯/欧国联）
- 用国家队 Elo（如 eloratings.net）+ 大赛历史比分，谨慎处理样本量小

## football-data.co.uk 联赛代码

| 中文 | 代码 | 中文 | 代码 |
|---|---|---|---|
| 英超 | E0 | 巴甲 | B1 |
| 西甲 | SP1 | 日职 | J1 |
| 德甲 | D1 | 墨超 | MEX |
| 意甲 | I1 | 美职 | MLS |
| 法甲 | F1 | 瑞典超 | S1 |
| 英冠 | E1 | 荷甲 | N1 |
| 葡超 | P1 | 苏超 | SC0 |

URL 格式：`https://www.football-data.co.uk/mmz4281/{赛季}/{代码}.csv`
赛季格式如 `2526`（2025/26）、`2425`（2024/25）。

## 赔率列命名（football-data.co.uk）

| 列 | 含义 |
|---|---|
| B365H/B365D/B365A | Bet365 初盘（主/平/客） |
| B365CH/B365CD/B365CA | Bet365 收盘 |
| PSH/PSD/PSA | Pinnacle 初盘 |
| PSCH/PSCD/PSCA | Pinnacle 收盘 |
| MaxH/MaxD/MaxA | 市场最高 |
| AvgH/AvgD/AvgA | 市场平均 |
| B365>2.5 / B365<2.5 | 大小球 2.5 初盘 |

## 已知坑（2026-10 实测）

1. **Pinnacle 列 2025-07-23 后系统性滞后**：CLV 计算改用市场平均（Avg）收盘，
   不再用 Pinnacle 收盘列。
2. 2025/26 赛季起新增一套赔率（开盘后初盘 + 收盘），字段名留意变化。
3. football-data.co.uk 免费但**仅限个人使用**，禁商用/批量爬虫/AI 训练。
4. FBRef 抓取需限速（约 3 秒/请求）；Understat 分支只限五大联赛+俄超。
5. sporttery.cn（竞彩官方）有腾讯云 EdgeOne 反爬，无公开 API——不做自动抓取，
   开售场次/官方赔率/开奖结果人工核对。
6. uefa.com / premierleague.com 的免 key 微服务是逆向文档化的非公开 API，
   随时可变，仅适合个人研究。
