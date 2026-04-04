#!/usr/bin/env python3
"""
平日毎朝8時に偉人の名言をSlack DMで送信するスクリプト
好みのテーマ: スティーブ・ジョブズ「Connecting the Dots」、人間万事塞翁が馬
"""

import os
import random
import json
import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_USER_ID = "U0973MEH3V0"

QUOTES = [
    {
        "text": "You can't connect the dots looking forward; you can only connect them looking backward. So you have to trust that the dots will somehow connect in your future.",
        "author": "Steve Jobs",
        "note": "Stanford大学卒業式スピーチ（2005）"
    },
    {
        "text": "Your time is limited, so don't waste it living someone else's life.",
        "author": "Steve Jobs",
        "note": "Stanford大学卒業式スピーチ（2005）"
    },
    {
        "text": "Stay hungry, stay foolish.",
        "author": "Steve Jobs",
        "note": "Stanford大学卒業式スピーチ（2005）"
    },
    {
        "text": "Remembering that you are going to die is the best way I know to avoid the trap of thinking you have something to lose.",
        "author": "Steve Jobs",
        "note": "Stanford大学卒業式スピーチ（2005）"
    },
    {
        "text": "人間万事塞翁が馬。\n（人生に起こることは、一見よいことも悪いことも、長い目で見ればどう転ぶかわからない）",
        "author": "淮南子（中国古典）",
        "note": "禍福はあざなえる縄のごとし"
    },
    {
        "text": "The only way to do great work is to love what you do. If you haven't found it yet, keep looking. Don't settle.",
        "author": "Steve Jobs"
    },
    {
        "text": "七転び八起き。\n（何度転んでも、また立ち上がれ）",
        "author": "日本のことわざ"
    },
    {
        "text": "It does not matter how slowly you go as long as you do not stop.",
        "author": "孔子（Confucius）"
    },
    {
        "text": "継続は力なり。\n（続けることに力が宿る）",
        "author": "日本のことわざ"
    },
    {
        "text": "The future belongs to those who believe in the beauty of their dreams.",
        "author": "Eleanor Roosevelt"
    },
    {
        "text": "In the middle of every difficulty lies opportunity.",
        "author": "Albert Einstein"
    },
    {
        "text": "雨垂れ石を穿つ。\n（小さな努力でも、積み重ねれば大きな成果につながる）",
        "author": "中国の古典"
    },
    {
        "text": "Success is not final, failure is not fatal: it is the courage to continue that counts.",
        "author": "Winston Churchill"
    },
    {
        "text": "艱難汝を玉にす。\n（困難があってこそ、人は磨かれ成長する）",
        "author": "日本のことわざ"
    },
    {
        "text": "The greatest glory in living lies not in never falling, but in rising every time we fall.",
        "author": "Nelson Mandela"
    },
    {
        "text": "Be yourself; everyone else is already taken.",
        "author": "Oscar Wilde"
    },
    {
        "text": "一期一会。\n（この出会いは二度と繰り返されない。だからこそ、今この瞬間を大切に）",
        "author": "茶道の精神（千利休）"
    },
    {
        "text": "Simplicity is the ultimate sophistication.",
        "author": "Leonardo da Vinci"
    },
    {
        "text": "初心忘るべからず。\n（始めたときの純粋な気持ちと志を、いつまでも忘れないようにせよ）",
        "author": "世阿弥"
    },
    {
        "text": "Two roads diverged in a wood, and I—I took the one less traveled by, and that has made all the difference.",
        "author": "Robert Frost",
        "note": "詩「The Road Not Taken」より"
    },
    {
        "text": "明日死ぬかのように生きよ。永遠に生きるかのように学べ。\nLive as if you were to die tomorrow. Learn as if you were to live forever.",
        "author": "Mahatma Gandhi"
    },
    {
        "text": "When you want something, all the universe conspires in helping you to achieve it.",
        "author": "Paulo Coelho",
        "note": "『アルケミスト』より"
    },
    {
        "text": "為せば成る、為さねば成らぬ何事も、成らぬは人の為さぬなりけり。\n（やろうとすれば何でもできる。できないのは、やろうとしていないだけだ）",
        "author": "上杉鷹山"
    },
    {
        "text": "Happiness is not something ready made. It comes from your own actions.",
        "author": "Dalai Lama XIV"
    },
    {
        "text": "知行合一。\n（知ることと行うことは一体であり、真に知っていれば自然と行動に移せる）",
        "author": "王陽明"
    },
    {
        "text": "Not everything that is faced can be changed, but nothing can be changed until it is faced.",
        "author": "James Baldwin"
    },
    {
        "text": "志を立てるのに、遅すぎるということはない。",
        "author": "佐藤一斎（『言志晩録』より）"
    },
    {
        "text": "The measure of intelligence is the ability to change.",
        "author": "Albert Einstein"
    },
    {
        "text": "冬来りなば春遠からじ。\n（どんなに辛い冬でも、必ず春はやってくる）",
        "author": "P.B. Shelley（和訳）"
    },
    {
        "text": "Logic will get you from A to Z; imagination will get you everywhere.",
        "author": "Albert Einstein"
    },
]

# 同じ名言が連続しないよう、最後に送った名言のインデックスを保存
STATE_FILE = os.path.join(os.path.dirname(__file__), "quote_state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_indices": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def pick_quote():
    state = load_state()
    last = state.get("last_indices", [])
    # 直近5件は除外して選ぶ
    available = [i for i in range(len(QUOTES)) if i not in last[-5:]]
    if not available:
        available = list(range(len(QUOTES)))
    idx = random.choice(available)
    last.append(idx)
    state["last_indices"] = last[-20:]  # 最大20件保持
    save_state(state)
    return QUOTES[idx]


def build_message(quote):
    today = datetime.date.today()
    weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
    dow = weekdays_ja[today.weekday()]
    date_str = f"{today.year}年{today.month}月{today.day}日（{dow}）"

    lines = [f":sunrise: *今日も一日、頑張りましょう！* — {date_str}", ""]
    lines.append(f"_{quote['text']}_")
    lines.append("")
    author_line = f"— *{quote['author']}*"
    if "note" in quote:
        author_line += f"  ({quote['note']})"
    lines.append(author_line)

    return "\n".join(lines)


def send_quote():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: SLACK_BOT_TOKEN is not set.")
        return False

    client = WebClient(token=token)
    quote = pick_quote()
    message = build_message(quote)

    try:
        client.chat_postMessage(channel=SLACK_USER_ID, text=message)
        print(f"Quote sent: {quote['author']}")
        return True
    except SlackApiError as e:
        print(f"Slack API error: {e.response['error']}")
        return False


if __name__ == "__main__":
    send_quote()
