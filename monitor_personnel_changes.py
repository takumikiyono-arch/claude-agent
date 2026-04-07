#!/usr/bin/env python3
"""
人事異動モニター
指定企業の人事異動情報を Google News RSS で監視し、
新着があれば自分自身（U0973MEH3V0）に Slack DM で通知する。
"""

import os
import json
import time
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN  = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID   = "U0973MEH3V0"
STATE_FILE   = Path(__file__).parent / "seen_personnel_news.json"
MAX_AGE_DAYS = 30      # 過去 N 日以内の記事のみ対象
REQUEST_INTERVAL = 2   # 企業間のリクエスト間隔（秒）

# 異動関連キーワード（タイトル/本文に含まれていれば通知対象）
KEYWORDS = [
    "人事異動", "就任", "退任", "新社長", "新会長", "新取締役", "昇進",
    "部長就任", "執行役員", "代表取締役", "役員", "異動", "転任",
]

COMPANIES = [
    "イワタニフーズ株式会社",
    "マルヤス工業株式会社",
    "株式会社ムロオ",
    "日本曹達株式会社",
    "株式会社トライフ",
    "株式会社バロックジャパンリミテッド",
    "NAX JAPAN株式会社",
    "ダイセーエブリー二十四株式会社",
    "山陽特殊製鋼株式会社",
    "サッポログループ物流株式会社",
    "DHLサプライチェーンジャパン株式会社",
    "ロジスティード東日本株式会社",
    "株式会社光洋",
    "ポリプラスチックス株式会社",
    "オイシックス・ラ・大地株式会社",
    "イセデリカ株式会社",
    "トクヤマ海陸運送株式会社",
    "臼杵運送株式会社",
    "泉海商運株式会社",
    "株式会社EVERYFOOD PRODUCTS",
    "伊藤忠食品株式会社",
    "伊藤ハム米久フーズ株式会社",
    "黒崎播磨株式会社",
    "アイエイチロジスティクスサービス株式会社",
    "株式会社関通",
    "福岡運輸株式会社",
    "松岡満運輸株式会社",
    "名古屋東部陸運株式会社",
    "株式会社啓和運輸",
    "株式会社日硝ハイウエー",
    "コストコホールセールジャパン株式会社",
    "株式会社スーパーバリュー",
    "株式会社JMホールディングス",
    "株式会社マルミヤストア",
    "伊藤ハム米久ホールディングス株式会社",
    "日立ジョンソンコントロールズ空調株式会社",
    "米久株式会社",
    "株式会社IJTT",
    "日華化学株式会社",
    "ミニストップ株式会社",
    "中外製薬株式会社",
    "日東ベスト株式会社",
    "株式会社日立製作所",
    "JFEスチール株式会社",
    "サッポロホールディングス株式会社",
    "山崎製パン株式会社",
    "株式会社サトー",
    "住友電気工業株式会社",
    "シャープ株式会社",
    "日本フルハーフ株式会社",
    "サッポロビール株式会社",
    "大同メタル工業株式会社",
    "GEヘルスケア・ジャパン株式会社",
    "東洋紙業株式会社",
    "ゼット株式会社",
    "アルフレッサ株式会社",
    "株式会社ハローズ",
    "アルフレッサホールディングス株式会社",
    "株式会社イエローハット",
    "株式会社LEOC",
    "フジッコ株式会社",
    "株式会社サングリーン",
    "株式会社天野回漕店",
    "株式会社クリエイトエス・ディー",
    "株式会社ヤマイシ",
    "日本特殊陶業株式会社",
    "株式会社キラックス",
    "ロジスティードコラボネクスト株式会社",
    "わらべや日洋ホールディングス株式会社",
    "ダイセーロジスティクス株式会社",
    "キャリーネット株式会社",
    "Umios株式会社",
    "株式会社ニッスイ",
    "キユーピー株式会社",
    "株式会社日清製粉グループ本社",
    "わらべや日洋食品株式会社",
    "山九株式会社",
    "株式会社近鉄ロジスティクス・システムズ",
    "日清物流株式会社",
    "SBSロジコム株式会社",
    "日清製粉株式会社",
    "株式会社二葉",
    "日水物流株式会社",
    "Umiosロジ株式会社",
]
# ─────────────────────────────────────────────────────────────────────────────

client = WebClient(token=SLACK_TOKEN)


def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))


def item_id(company: str, title: str, link: str) -> str:
    raw = f"{company}|{title}|{link}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_relevant(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    return any(kw in text for kw in KEYWORDS)


def fetch_news(company: str) -> list[dict]:
    """Google News RSS から企業の人事異動情報を取得する。"""
    query = f"{company} 人事異動"
    encoded = urllib.parse.quote(query)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded}&hl=ja&gl=JP&ceid=JP:ja"
    )

    headers = {"User-Agent": "Mozilla/5.0 (compatible; SlackPersonnelBot/1.0)"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"[WARN] fetch failed for {company}: {e}")
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"[WARN] XML parse error for {company}: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    items = []

    for item in root.iter("item"):
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link")  or "").strip()
        pub_str = (item.findtext("pubDate") or "").strip()
        desc    = (item.findtext("description") or "").strip()

        # 日付フィルター
        try:
            pub_dt = parsedate_to_datetime(pub_str).astimezone(timezone.utc)
            if pub_dt < cutoff:
                continue
        except Exception:
            pass  # 日付不明なら通過させる

        if not is_relevant(title, desc):
            continue

        # 日付を JST で表示用にフォーマット
        try:
            jst = pub_dt.astimezone(timezone(timedelta(hours=9)))
            pub_display = jst.strftime("%Y-%m-%d %H:%M JST")
        except Exception:
            pub_display = pub_str

        items.append({
            "company": company,
            "title":   title,
            "link":    link,
            "pub":     pub_display,
        })

    return items


def get_dm_channel(user_id: str) -> str:
    resp = client.conversations_open(users=user_id)
    return resp["channel"]["id"]


NOTIFY_CHANNEL = "C0AS4CZGZJL"   # #清野通知bot


def send_dm(text: str) -> None:
    client.chat_postMessage(channel=NOTIFY_CHANNEL, text=f"<@{MY_USER_ID}> {text}", mrkdwn=True)


def format_notification(new_items: list[dict]) -> str:
    # 企業ごとにまとめる
    from collections import defaultdict
    by_company: dict[str, list] = defaultdict(list)
    for item in new_items:
        by_company[item["company"]].append(item)

    lines = [f":newspaper: *人事異動情報 — 新着 {len(new_items)} 件*\n"]
    for company, items in by_company.items():
        lines.append(f"*【{company}】*")
        for it in items:
            lines.append(f"  • {it['pub']}  {it['title']}")
            lines.append(f"    {it['link']}")
    lines.append("\n_Claude が自動モニタリング（毎日チェック）_")
    return "\n".join(lines)


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    print(f"[INFO] Check started at {now}")

    seen     = load_seen()
    new_items: list[dict] = []

    for company in COMPANIES:
        try:
            articles = fetch_news(company)
        except Exception as e:
            print(f"[ERROR] {company}: {e}")
            articles = []

        for article in articles:
            uid = item_id(company, article["title"], article["link"])
            if uid not in seen:
                seen.add(uid)
                new_items.append(article)
                print(f"[NEW] {company}: {article['title']}")

        time.sleep(REQUEST_INTERVAL)

    save_seen(seen)

    if not new_items:
        print("[INFO] 新着の人事異動情報なし。通知はスキップします。")
        return

    print(f"[INFO] {len(new_items)} 件の新着情報を DM 送信します。")
    # 1メッセージが長すぎる場合は分割（Slack上限 4000字目安）
    msg = format_notification(new_items)
    if len(msg) <= 4000:
        send_dm(msg)
    else:
        # 企業ごとに分割
        from collections import defaultdict
        by_company: dict[str, list] = defaultdict(list)
        for item in new_items:
            by_company[item["company"]].append(item)

        header = f":newspaper: *人事異動情報 — 新着 {len(new_items)} 件*\n"
        send_dm(header)
        chunk_lines: list[str] = []
        for company, items in by_company.items():
            block = [f"*【{company}】*"]
            for it in items:
                block.append(f"  • {it['pub']}  {it['title']}")
                block.append(f"    {it['link']}")
            chunk_lines.extend(block)
            if len("\n".join(chunk_lines)) > 3500:
                send_dm("\n".join(chunk_lines))
                chunk_lines = []
        if chunk_lines:
            send_dm("\n".join(chunk_lines))

    print("[INFO] DM 送信完了。")


if __name__ == "__main__":
    main()
