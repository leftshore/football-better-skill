#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据采集层 fetch_data.py
=======================
统一拉取足彩分析所需的历史比分、赔率、Elo、xG 数据，输出统一格式。

数据源与覆盖范围（实测结论，2026-10-08）：
------------------------------------------------
1) football-data.co.uk（免费 CSV 直下，无需 key）
   - 22 个欧洲联赛（1993/94 起）+ 16 个全球顶级联赛（2012/13 起，
     含：巴甲、日职、墨超、美职、瑞典超、中超——竞彩常开联赛几乎全覆盖）
   - 字段：全场/半场比分、开盘/收盘赔率（胜平负/大小球/亚盘，最多10家庄）、
     射门/角球/红黄牌/裁判
   - ⚠️ 已知坑：
     a) 仅限个人使用，禁止商用/批量爬虫/AI训练；
     b) 2025-07-23 起 Pinnacle 公开 API 数据系统性滞后——做 CLV 分析时
        Pinnacle 收盘列不可用，改用 Bet365/市场平均收盘；
     c) 2025/26 赛季起新增一套赔率（开盘后初盘 + 收盘），字段名留意变化。
2) ClubElo（免费 HTTP API，无需 key）
   - 覆盖多数欧洲联赛俱乐部，按轮重算的 Elo 评分 + 历史
   - 注意：南美/日韩联赛覆盖弱或没有，缺失时 fallback 用比分拟合的 Dixon-Coles
3) soccerdata（统一爬虫库，需安装，本地缓存）
   - 一行代码统一拉 FBref / Understat / ClubElo / Football-Data.co.uk /
     ESPN / Sofascore / SoFIFA / WhoScored
   - ⚠️ 已知坑：FBref 抓取需限速（~3 秒/请求），Understat 分支只限五大联赛+俄超
4) xG 数据（Understat / FBRef）
   - ⚠️ 已知坑：xG 仅覆盖五大联赛 + 俄超；
     日职/韩K/巴甲/美职/墨超是 xG 荒漠——这些联赛只用比分 + Elo + 收盘赔率建模
5) sporttery.cn（竞彩官方信息发布平台）
   - ⚠️ 有腾讯云 EdgeOne 反爬，无公开 API——本脚本不做自动抓取；
     开售场次/官方赔率/开奖结果以该站人工核对为准
6) StatsBomb open-data：赛事级（世界杯/欧冠决赛等），非全联赛，免 key

本脚本不需要任何 key / token，全部走免费公开渠道。
"""

from __future__ import annotations

import io
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# 联赛代码 → football-data.co.uk 文件名映射（以其官网为准）
# https://www.football-data.co.uk/data.php
# ---------------------------------------------------------------------------
FOOTBALL_DATA_LEAGUE_CODES = {
    # 五大联赛
    "英超": "E0", "西甲": "SP1", "德甲": "D1", "意甲": "I1", "法甲": "F1",
    "英冠": "E1", "荷甲": "N1", "葡超": "P1", "苏超": "SC0",
    # 竞彩常开：南美/亚洲/北美
    "巴甲": "B1", "日职": "J1", "墨超": "MEX", "美职": "MLS", "瑞典超": "S1",
    # 欧战/国家队用其他源
}

FD_BASE = "https://www.football-data.co.uk/mmz4281"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (jingcai-betting-skill; research-only) "
                  "jingcai-betting-skill/0.1",
})

# 球队名映射 fallback：football-data.co.uk 队名 → 统一中文名
# 抓不到的队名原样透传，不编造
TEAM_NAME_MAP = {
    "Arsenal": "阿森纳", "Chelsea": "切尔西", "Liverpool": "利物浦",
    "Man City": "曼城", "Man United": "曼联", "Tottenham": "热刺",
    "Newcastle": "纽卡斯尔", "Brighton": "布莱顿", "Aston Villa": "维拉",
    "West Ham": "西汉姆", "Everton": "埃弗顿", "Wolves": "狼队",
    "Fulham": "富勒姆", "Crystal Palace": "水晶宫", "Brentford": "布伦特福德",
    "Bournemouth": "伯恩茅斯", "Nott'm Forest": "诺丁汉森林",
    "Leicester": "莱斯特城", "Southampton": "南安普顿", "Ipswich": "伊普斯维奇",
    "Santos": "桑托斯", "Flamengo RJ": "弗拉门戈",
}


def team_zh(name: str) -> str:
    """球队名 → 中文，映射缺失时原样返回（不编造）。"""
    return TEAM_NAME_MAP.get(name, name)


# ---------------------------------------------------------------------------
# 联赛分级（SKILL.md 流水线条件分支用）
#   A 级 xG 联赛：Understat/FBRef 有 xG → xG 增强分支
#   B 级数据荒漠：无 xG → 比分 + Elo + 收盘赔率分支（不要编造 xG）
#   C 级国家队赛事：样本小，置信度上限"中"
# ---------------------------------------------------------------------------
TIER_A_XG = {"英超", "西甲", "德甲", "意甲", "法甲", "俄超",
             "E0", "SP1", "D1", "I1", "F1"}
TIER_B_DESERT = {"日职", "韩K", "巴甲", "美职", "墨超", "芬超",
                 "J1", "B1", "MLS", "MEX", "S1"}


def league_tier(league: str) -> str:
    """返回 'A'(xG联赛) / 'B'(数据荒漠) / 'C'(其他/国家队)。"""
    if league in TIER_A_XG:
        return "A"
    if league in TIER_B_DESERT:
        return "B"
    return "C"


def branch_hint(league: str) -> str:
    tier = league_tier(league)
    hints = {
        "A": "xG 增强分支：Understat/FBRef 取 xG 叠加 Dixon-Coles 先验",
        "B": "荒漠分支：只用比分 + Elo + 收盘赔率；无 xG，不要编造",
        "C": "国家队/其他：Elo + 大赛历史，置信度上限为中",
    }
    return hints[tier]


# ---------------------------------------------------------------------------
# 1. football-data.co.uk：历史比分 + 多庄开/收盘赔率
# ---------------------------------------------------------------------------
def fetch_football_data(league: str, seasons=("2526", "2425")) -> pd.DataFrame:
    """
    拉取某联赛多个赛季的全部比赛 CSV（含比分+赔率），合并返回 DataFrame。

    参数 league：中文联赛名（如 "英超"）或 football-data 代码（如 "E0"）。
    返回：DataFrame，至少包含 Date, HomeTeam, AwayTeam, FTHG, FTAG,
         B365H/B365D/B365A(开盘), BSH/BSD/BSA(收盘) 等赔率列。
    """
    code = FOOTBALL_DATA_LEAGUE_CODES.get(league, league)
    frames = []
    for season in seasons:
        url = f"{FD_BASE}/{season}/{code}.csv"
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df["season"] = season
            frames.append(df)
        except requests.RequestException as exc:  # pragma: no cover
            print(f"[fetch] 拉取 {url} 失败: {exc}", file=sys.stderr)
    if not frames:
        raise RuntimeError(f"football-data.co.uk 拉取失败：{league}，检查网络或联赛代码")
    return pd.concat(frames, ignore_index=True)


def recent_matches(df: pd.DataFrame, home: str, away: str, n: int = 10):
    """取两队各自最近 n 场联赛（用于近期状态 / Dixon-Coles 拟合）。"""
    for col in ("HomeTeam", "AwayTeam", "FTHG", "FTAG", "Date"):
        if col not in df.columns:
            raise KeyError(f"CSV 缺少字段 {col}")
    df = df.dropna(subset=["FTHG", "FTAG"]).copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.sort_values("Date")
    home_games = df[(df["HomeTeam"] == home) | (df["AwayTeam"] == home)].tail(n)
    away_games = df[(df["HomeTeam"] == away) | (df["AwayTeam"] == away)].tail(n)
    return home_games, away_games


# ---------------------------------------------------------------------------
# 2. ClubElo：球队 Elo 评分（免费 HTTP API）
# ---------------------------------------------------------------------------
def fetch_clubelo(team: str):
    """
    从 ClubElo 取某球队当前 Elo 与排名。
    返回 dict {elo, rank, ...}，失败返回 None（上层 fallback）。
    南美/日韩球队多半没有——这是已知坑，不要当错误。
    """
    try:
        r = SESSION.get(f"http://api.clubelo.com/{team}", timeout=20)
        if r.status_code != 200:
            return None
        lines = r.text.strip().splitlines()
        if not lines:
            return None
        # api.clubelo.com 返回 CSV：Rank,Club,Elo,Level,Country,From,To
        last = lines[-1].split(",")
        return {
            "rank": int(last[0]),
            "club": last[1],
            "elo": float(last[2]),
            "country": last[4],
        }
    except Exception as exc:  # pragma: no cover
        print(f"[fetch] ClubElo 查询 {team} 失败: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 3. soccerdata：统一爬虫（FBRef/Understat/ClubElo 口径统一）
# ---------------------------------------------------------------------------
def fetch_via_soccerdata(league: str, seasons=("2024-2025", "2025-2026")):
    """
    用 soccerdata 拉取某联赛的赛程/比分（Football-Data.co.uk 后端）。
    xG 荒漠联赛（日职/韩K/巴甲/美职/墨超）不要调用 Understat 分支。
    """
    try:
        import soccerdata as sd
    except ImportError:  # pragma: no cover
        print("[fetch] soccerdata 未安装：pip install soccerdata", file=sys.stderr)
        return None
    code = FOOTBALL_DATA_LEAGUE_CODES.get(league, league)
    try:
        fd = sd.FootballData(leagues=code, seasons=list(seasons))
        return fd.read_schedule()
    except Exception as exc:  # pragma: no cover
        print(f"[fetch] soccerdata 拉取失败: {exc}", file=sys.stderr)
        return None


def fetch_xg(league: str, season: str = "2025-2026"):
    """
    仅五大联赛 + 俄超可取 xG（Understat via soccerdata）。
    非覆盖联赛返回 None 并打印提示——不要用假 xG。
    """
    XG_LEAGUES = {"英超", "西甲", "德甲", "意甲", "法甲",
                  "E0", "SP1", "D1", "I1", "F1"}
    if league not in XG_LEAGUES:
        print(f"[fetch] {league} 是 xG 荒漠联赛，跳过 xG（用比分+Elo+收盘赔率建模）")
        return None
    try:
        import soccerdata as sd
    except ImportError:
        return None
    code = FOOTBALL_DATA_LEAGUE_CODES.get(league, league)
    # Understat 联赛代码映射（soccerdata 1.9+ 用全名）
    understat_codes = {"E0": "ENG-Premier League", "SP1": "ESP-La Liga",
                       "D1": "GER-Bundesliga", "I1": "ITA-Serie A",
                       "F1": "FRA-Ligue 1"}
    try:
        u = sd.Understat(leagues=understat_codes[code], seasons=[season])
        return u.read_team_match_stats()
    except Exception as exc:  # pragma: no cover
        print(f"[fetch] xG 拉取失败: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 主入口：一次拉取一场比赛所需的全部数据，打包成 JSON
# ---------------------------------------------------------------------------
def build_match_pack(league: str, home: str, away: str,
                     out: Path | None = None) -> dict:
    """
    给定联赛+主客队（football-data.co.uk 队名拼写），拉取：
      - 近 2 赛季全部比赛（含比分+赔率）
      - 两队近 10 场
      - ClubElo（欧洲球队）
      - xG（五大联赛才有）
    返回 dict，可 json.dump 落盘。
    """
    df = fetch_football_data(league)
    home_games, away_games = recent_matches(df, home, away)
    elo_home = fetch_clubelo(home)
    elo_away = fetch_clubelo(away)
    xg = fetch_xg(league)
    xg_note = "available" if xg is not None else "xG desert — use scores+Elo+closing odds"

    pack = {
        "league": league,
        "home": home, "home_zh": team_zh(home),
        "away": away, "away_zh": team_zh(away),
        "fetched_at": date.today().isoformat(),
        "n_matches_total": len(df),
        "home_recent": home_games.to_dict("records"),
        "away_recent": away_games.to_dict("records"),
        "full_history": df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].to_dict("records"),
        "elo_home": elo_home, "elo_away": elo_away,
        "xg": xg_note,
    }
    if out:
        out.write_text(json.dumps(pack, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[fetch] 数据包已写入 {out}")
    return pack


if __name__ == "__main__":
    # 用法示例：
    #   python scripts/fetch_data.py 英超 Arsenal Chelsea
    if len(sys.argv) != 4:
        print("用法: python scripts/fetch_data.py <联赛> <主队> <客队>")
        print("示例: python scripts/fetch_data.py 英超 Arsenal Chelsea")
        sys.exit(1)
    league, home, away = sys.argv[1], sys.argv[2], sys.argv[3]
    slug = f"{league}_{home}_vs_{away}".replace(" ", "_")
    build_match_pack(league, home, away, out=Path(f"data/{slug}.json"))
