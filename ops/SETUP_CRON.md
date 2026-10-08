# 定时结算配置（ops/SETUP_CRON.md）

目标：比赛结束后自动"拉比分 → 结算追踪表 → 回填收盘赔率算 CLV"，
无需人工盯盘。

## 方案 A：cron（Linux/macOS 服务器）

```bash
# 每天 08:00 对昨日有比赛的 pack 自动结算
0 8 * * * cd ~/workspace/jingcai-betting-skill && \
  for p in data/*.json; do \
    .venv/bin/python scripts/settle.py --auto --pack "$p"; \
  done >> logs/settle.log 2>&1

# 每周一 09:00 输出校准报告
0 9 * * 1 cd ~/workspace/jingcai-betting-skill && \
  .venv/bin/python scripts/calibration.py --n 50 >> logs/calibration.log 2>&1
```

## 方案 B：Muse cron（本机助手）

用 `cron.add` 创建定时任务，指令同上。优点：跑在本机，
结算结果可直接回聊；缺点：本机需开机。

## 注意事项

1. **只结算已完赛**：settle.py --auto 找不到完赛记录时自动跳过，
   不会误结算未开赛场次。
2. **收盘赔率来源**：football-data.co.uk 的 Avg（市场平均）列；
   Pinnacle 收盘列 2025-07-23 后系统性滞后，不用。
3. **方向映射是启发式**：pick 文本无法判断方向时记"平"并打印提示，
   需人工用 `settle.py manual` 复核修正。
4. **data/*.json 不入库**：pack 含运行时数据，.gitignore 已排除；
   cron 跑之前确保 pack 文件存在（fetch_data.py 生成）。
5. 结算后 `tracker.py summary` 自动同步 `data/tracker.md`。
