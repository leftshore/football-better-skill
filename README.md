# 竞彩足球智能分析 Skill

一句话触发、自动完成「数据采集 → 建模 → 多方交叉验证 → 按固定框架输出 → 记入追踪表」的开源足彩分析 Skill。

## 功能

- **一句话触发**：用户说"单关分析，桑托斯vs弗拉门戈"，自动跑完全流水线
- **数据准确**：football-data.co.uk（30 年比分+多庄赔率）+ ClubElo + soccerdata 统一口径，全部免费公开渠道，无需 key
- **精准分析**：penaltyblog 的 Dixon-Coles 模型算胜平负/大小球概率，overround removal 去水算市场隐含概率，模型 vs 市场找 edge
- **多方交叉验证**：5 个固定账号分工 + BBC/Sky/欧足联官网/懂球帝/虎扑/竞彩官方，只取事实不取结论
- **铁律框架**：七条铁律 + 资金纪律硬编码进流水线，"观望（0 元）"是一等输出
- **长期校准**：每单记入置信度-结果追踪表，用 CLV 而非盈亏评价过程质量

## 快速开始

```bash
git clone https://github.com/<你的用户名>/jingcai-betting-skill.git
cd jingcai-betting-skill
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Step 0：触发前检查——开球时间、赔率新鲜度、首发状态（成品/半成品）
# Step 1：拉数据（示例：英超阿森纳vs切尔西）
python scripts/fetch_data.py 英超 Arsenal Chelsea

# Step 2：建模（读 data/*.json，输出模型概率 vs 市场概率 + edge，自动冻结预测日志）
python scripts/model.py --pack data/英超_Arsenal_vs_Chelsea.json \
    --book-odds "2.10,3.40,3.60" --lineup 未出 --odds-at "2026-10-09T00:30:00+08:00"

# Step 3：交叉验证：按 playbooks/crosscheck.md 执行

# Step 4：按 playbooks/output_template.md 输出（含固定 JSON 块）

# Step 5a：从 JSON 自动记账（含 CLV）
python scripts/tracker.py add-from-json analysis.json

# Step 5b：赛后结算（自动拉比分 + 回填收盘赔率算 CLV）
python scripts/settle.py --auto --pack data/英超_Arsenal_vs_Chelsea.json
# 或手动：python scripts/settle.py manual --id 1 --score "2-1" --result 胜

# 校准：每 50 单输出 Brier 评分 + 置信度校准报告
python scripts/calibration.py --n 50
# CLV 汇总
python scripts/tracker.py clv
```

## 八项能力

| # | 能力 | 落点 |
|---|---|---|
| 1 | SKILL.md 瘦身 + 渐进披露 | 主文件只留 frontmatter/触发器/流水线索引，联赛手册、赔率术语、铁律全文进 `references/` |
| 2 | 结构化输出契约 | 输出模板末尾固定 JSON 块；`tracker.py add-from-json` 自动解析记账 |
| 3 | CLV 自动记账 | 每单记录投注赔率 vs 收盘赔率（市场平均 Avg 列）；`tracker.py clv` 输出正 CLV 占比/均值 |
| 4 | 版本化预测日志 | 每次分析冻结"赔率快照+首发快照+模型版本+数据日期"到 `predictions/predictions.jsonl`，防事后修改 |
| 5 | 联赛分级分支 | xG 联赛（英超/西甲/德甲/意甲/法甲/俄超）走 xG 增强分支；数据荒漠联赛（日职/韩K/巴甲/美职/墨超等）走比分+Elo+收盘赔率分支 |
| 6 | Brier 评分 + 校准报告 | `scripts/calibration.py` 每 N 单（默认 50）输出标称概率 vs 真实命中率 |
| 7 | 触发前检查清单 | Step 0：开球时间校验、赔率新鲜度、首发状态→输出显性标注"成品"/"半成品" |
| 8 | 赛后自动结算 | `scripts/settle.py`（手动/自动）+ `ops/SETUP_CRON.md` 定时配置 |

## 数据来源

| 来源 | 内容 | 费用 | 备注 |
|---|---|---|---|
| football-data.co.uk | 30 年比分+多庄开/收盘赔率 | 免费（个人用） | Pinnacle 列 2025-07-23 后滞后，CLV 改用市场平均收盘 |
| ClubElo | 球队 Elo 评分 | 免费 | 南美/日韩覆盖弱，缺失 fallback |
| soccerdata | FBRef/Understat/ClubElo 统一爬虫 | 免费 | FBRef 需限速；Understat 只限五大联赛+俄超 |
| Understat/FBRef | xG | 免费 | **xG 荒漠**：日职/韩K/巴甲/美职/墨超无 xG |
| sporttery.cn | 竞彩官方开售/赔率/开奖 | 免费 | 有反爬，不做自动抓取，人工核对 |

## 免责声明

本项目仅供**研究与娱乐**，输出的概率与分析**不构成任何投注建议**。
足球比赛存在巨大方差，任何模型都无法保证盈利（实证：以庄家赔率为基准，
没有公开模型能稳定超越市场）。请理性对待，量力而行。
"稳赚/内幕/包赢"、收费带单、索取博彩账户密码的均为骗局，请直接拉黑。

## License

MIT
