# 赔率术语（references/ 渐进披露）

## 基础

- **欧洲赔率（decimal）**：投注 100 元、赔率 2.00，命中返还 200 元（含本金）。
- **隐含概率**：1 / 赔率。如 2.00 → 50%。
- **Overround（抽水/水位）**：庄家把三项隐含概率加总调到 >100%，
  超出的部分就是庄家的利润 margin。如三项加总 107%，水位 ≈ 6.5%。

## 去水（Overround removal）

把庄家赔率中的水位剥离，还原市场真实的隐含概率。
本 skill 用 penaltyblog 的 `calculate_implied`，默认 multiplicative 方法，
另有 Shin、logarithmic、power、odds-ratio 等方法可选。
去水后的概率加总 = 100%，可直接与模型概率对比找 edge。

## edge（期望边际）

`edge = 模型概率 − 去水后市场隐含概率`
- edge ≥ +5%：候选机会，需至少 2 个独立事实源佐证才升级置信度
- edge 接近 0 或为负：定价公允 → 观望（0 元）

## CLV（Closing Line Value，收盘赔率价值）

`CLV = 投注时赔率 − 赛前收盘赔率`（方向：拿到比收盘更好的价格 = 正 CLV）
- 持续正 CLV 是长期盈利的最强早期证据，比实际盈亏早数百单显现（方差小得多）
- 本 skill 的追踪表自动记录每单 CLV，用收盘市场平均（Avg）列计算
- 注意：football-data.co.uk 的 Pinnacle 收盘列 2025-07 后滞后，改用 Avg

## Kelly（凯利注码）

`f = (bp − q) / b`，其中 b=净赔率，p=模型概率，q=1−p。
实战用**分数 Kelly**（如 1/4 Kelly）控制波动。
penaltyblog.betting 提供 `kelly_criterion` / `multiple_kelly_criterion`。

## Brier 评分

`(预测概率 − 实际结果)²` 的均值，越小越好。
完美预测 = 0，瞎猜 50% ≈ 0.25。
本 skill 的 `scripts/calibration.py` 按高/中/低置信度分组输出 Brier，
检验"标称概率 vs 真实命中率"是否校准。

## 亚洲盘 / 大小球

- 亚洲盘（AH）：让球盘口，如主让 0.5；走水（push）退本金
- 大小球 2.5：总进球 >2.5 为大，<2.5 为小；2.5 无走水
- penaltyblog 的 `FootballProbabilityGrid.totals()` 处理整数/四分之一盘的走水
