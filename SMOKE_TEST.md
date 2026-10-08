# 冒烟测试报告

- 测试日期：2026-10-09（CST）
- 测试比赛：英超 Chelsea 1-1 Arsenal（2025-11-30，已完赛，真实数据）
- 环境：Python 3.12 venv，penaltyblog 1.13.1，soccerdata 1.9.1，pandas 3.0.6
- 结论：**全部通过**

## 1. 数据采集 scripts/fetch_data.py ✅

- `python scripts/fetch_data.py 英超 Chelsea Arsenal`
- football-data.co.uk E0 两个赛季（2425+2526）共 **760 场**真实比赛拉取成功
- 球队名映射 fallback 正常（映射缺失原样透传，不编造）
- 联赛分级函数 `league_tier("英超")` → A，`league_tier("巴甲")` → B，分支提示正确

### 已知外部问题（非代码 bug）

| 现象 | 原因 | 处理 |
|---|---|---|
| ClubElo API 返回 HTTP 502 | api.clubelo.com 当时不可用 | `fetch_clubelo` 返回 None，上层 fallback 纯比分拟合 |
| soccerdata Understat 拉 xG 失败 | "Failed to download the required TLS library"（环境限制） | `fetch_xg` 返回 None，提示走荒漠分支；soccerdata 1.9.1 联赛代码已修正为全名（如 ENG-Premier League） |

## 2. 建模 scripts/model.py ✅

- `python scripts/model.py --pack data/英超_Chelsea_vs_Arsenal.json --book-odds "3.4,3.3,2.2" --total-odds "2.10,1.72" --lineup 已出`
- Dixon-Coles 拟合 760 场，输出：
  - 模型 1X2：主胜 20.47% / 平 25.07% / 客胜 54.46%（加总=100% ✓）
  - 去水后市场：27.97% / 28.81% / 43.22%，水位 5.17% ✓
  - edge：客胜 +11.24% → 命中候选阈值（实际 1-1，方差内）
  - 大小球：模型大 53.56% vs 市场 45.03%，edge +8.53%
  - 极端值标记：无（铁律6）
- 版本化预测日志：`predictions/predictions.jsonl` 冻结成功
  （model_version=penaltyblog-1.13.1/dixon-coles，含赔率快照+首发快照+数据日期）

## 3. 追踪表 scripts/tracker.py ✅

- `add-from-json`：解析输出模板 JSON 块，记入成功（含对冲信息）
- `settle --closing-odds`：CLV = 2.20 − 2.46 = **−0.26** ✓
- `clv`：正 CLV 占比/均值/中位输出正常
- `summary`：纪律账三行（本金/累计盈亏/距红线）+ 置信度校准正常
- **单注 1500 元被拦截**（上限 1000）✓

## 4. 赛后结算 scripts/settle.py ✅

- `settle.py auto --pack ...`：自动找到 Chelsea 1-1 Arsenal，
  将"阿森纳胜"判为"负" ✓
- 收盘赔率方向映射 bug 已修复：pick 含客队名 → 取 AvgCA 列
  （修复前误取 AvgCH，CLV −0.81；修复后 −0.26 ✓）
- `manual` / `list` 正常

## 5. 校准报告 scripts/calibration.py ✅

- 3 单测试数据：高/中两档 Brier=0.2916，偏离>15% 正确告警
- 总体 Brier 输出正常（参考：瞎猜≈0.25）

## 6. 编译检查 ✅

- 全部 5 个脚本 `py_compile` 通过
- 无 key/token 硬编码（grep 确认）
