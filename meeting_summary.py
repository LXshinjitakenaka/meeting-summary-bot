"""
Meeting Summary Bot - v4
Google Calendar から今週（月〜金）の承諾済み会議を集計し、
Slack の自分宛 DM に投稿する
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

MY_EMAIL    = os.environ["MY_EMAIL"]
SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
SLACK_USER_ID = os.environ.get("SLACK_USER_ID", "U041CPB9927")  # 竹中さんのSlackユーザーID
JST         = timezone(timedelta(hours=9))

SKIP_TITLES = {
    "移動", "ブロック", "病院",
    "基本作業時間（MTG入れるときは相談してください）",
    "自宅", "オフィス", "杉六小CS",
    "今週の授業予定確認/公募確認",
}

CATEGORY_KEYWORDS = {
    "全社": ["Daily-Checkin", "生徒総会"],
    "1on1": [
        "1on1", "1ON1", "Shinji /", "/ Shinji",
        "たけさん x", "たけさん×", "たけちゃん", "たけさん/",
        "Shiho/Shinji", "Takuya / Shinji", "えもちゃん",
        "ゆきむ", "emochanたけいた", "業務１on１",
    ],
}

CATEGORIES = ["社内定例", "社外", "1on1", "全社"]
CAT_EMOJI  = {"社内定例": "🏢", "社外": "🤝", "1on1": "👤", "全社": "📢"}


def build_calendar_service():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        info  = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
    else:
        creds = Credentials.from_service_account_file(
            "credentials.json",
            scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
    return build("calendar", "v3", credentials=creds)


def fetch_events(service, time_min, time_max):
    events, page_token = [], None
    while True:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=250,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()
        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return events


def get_duration_minutes(ev):
    s = ev.get("start", {}).get("dateTime")
    e = ev.get("end",   {}).get("dateTime")
    if not s or not e:
        return 0
    return int((datetime.fromisoformat(e) - datetime.fromisoformat(s)).total_seconds() / 60)


def is_solo(ev):
    attendees = ev.get("attendees", [])
    if not attendees:
        return True
    real = [a for a in attendees if not a.get("email", "").endswith("@resource.calendar.google.com")]
    return len(real) <= 1


def get_my_status(ev):
    for a in ev.get("attendees", []):
        if a.get("self") or a.get("email") == MY_EMAIL:
            return a.get("responseStatus", "")
    return ev.get("myResponseStatus", "")


def is_accepted(ev):
    return (not is_solo(ev)) and get_my_status(ev) == "accepted"


def categorize(ev):
    title     = ev.get("summary", "")
    attendees = ev.get("attendees", [])
    external  = [
        a for a in attendees
        if "@lxdesign.me" not in a.get("email", "")
        and not a.get("email", "").endswith("@resource.calendar.google.com")
    ]
    if any(k in title for k in CATEGORY_KEYWORDS["全社"]) or \
       any("lx_all" in a.get("email", "") for a in attendees):
        return "全社"
    if any(k in title for k in CATEGORY_KEYWORDS["1on1"]):
        return "1on1"
    if external:
        return "社外"
    return "社内定例"


def filter_and_categorize(events):
    result = []
    for ev in events:
        if ev.get("eventType") in ("workingLocation", "outOfOffice"):
            continue
        if not ev.get("start", {}).get("dateTime"):
            continue
        if ev.get("summary", "") in SKIP_TITLES:
            continue
        if not is_accepted(ev):
            continue
        minutes = get_duration_minutes(ev)
        if minutes == 0:
            continue
        result.append({
            "title":    ev.get("summary", "（無題）"),
            "category": categorize(ev),
            "minutes":  minutes,
            "date":     ev["start"]["dateTime"][:10],
            "time":     ev["start"]["dateTime"][11:16],
        })
    return result


def fmt_time(minutes):
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if m else f"{h}h"


def make_bar(minutes, total, width=16):
    if total == 0:
        return "░" * width
    filled = round(minutes / total * width)
    return "█" * filled + "░" * (width - filled)


def weekday_ja(date_str):
    d  = datetime.strptime(date_str, "%Y-%m-%d")
    WD = ["月", "火", "水", "木", "金", "土", "日"]
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def build_blocks(events, week_start, week_end):
    totals = defaultdict(lambda: {"minutes": 0, "count": 0})
    for ev in events:
        totals[ev["category"]]["minutes"] += ev["minutes"]
        totals[ev["category"]]["count"]   += 1

    total_min   = sum(v["minutes"] for v in totals.values())
    total_count = sum(v["count"]   for v in totals.values())
    fri = week_end - timedelta(days=1)
    date_range = f"{week_start.month}/{week_start.day}(月)〜{fri.month}/{fri.day}(金)"

    blocks = []
    blocks.append({"type": "header", "text": {"type": "plain_text", "text": "📅 今週の会議実績レポート", "emoji": True}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{date_range}*"}})
    blocks.append({"type": "divider"})

    lines = [f"*合計　{fmt_time(total_min)}　/ {total_count}件*\n"]
    for cat in CATEGORIES:
        v = totals[cat]
        if v["minutes"] == 0:
            continue
        pct = round(v["minutes"] / total_min * 100) if total_min else 0
        bar = make_bar(v["minutes"], total_min)
        lines.append(f"{CAT_EMOJI[cat]} *{cat}*　`{bar}`　{fmt_time(v['minutes'])}　{v['count']}件　_{pct}%_")
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
    blocks.append({"type": "divider"})

    by_day = defaultdict(list)
    for ev in sorted(events, key=lambda x: (x["date"], x["time"])):
        by_day[ev["date"]].append(ev)

    day_lines = ["*📆 曜日別内訳*"]
    for date_str in sorted(by_day):
        day_evs = by_day[date_str]
        day_min = sum(e["minutes"] for e in day_evs)
        day_lines.append(f"　*{weekday_ja(date_str)}*　{fmt_time(day_min)}　{len(day_evs)}件")
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(day_lines)}})
    blocks.append({"type": "divider"})

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*📋 全会議リスト（承諾済み・複数人）*"}})

    by_cat = defaultdict(list)
    for ev in sorted(events, key=lambda x: (x["date"], x["time"])):
        by_cat[ev["category"]].append(ev)

    for cat in CATEGORIES:
        evs = by_cat[cat]
        if not evs:
            continue
        cat_min = sum(e["minutes"] for e in evs)
        lines   = [f"{CAT_EMOJI[cat]} *{cat}*　_{fmt_time(cat_min)} / {len(evs)}件_"]
        for ev in evs:
            lines.append(f"　• {weekday_ja(ev['date'])} {ev['time']}　{ev['title']}　_{fmt_time(ev['minutes'])}_")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})

    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "※ accepted + 複数人のみ集計。移動・ブロック・workingLocation は除外。"}]})
    return blocks


def post_dm(blocks):
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/json",
    }

    # ① ユーザーIDで DM チャンネルを開く（チャンネルIDではなくユーザーIDを渡す）
    print(f"Slack ユーザー ID: {SLACK_USER_ID}")
    open_resp = requests.post(
        "https://slack.com/api/conversations.open",
        headers=headers,
        json={"users": SLACK_USER_ID},  # ← ユーザーIDを渡す
        timeout=10,
    )
    open_data = open_resp.json()
    print(f"conversations.open: ok={open_data.get('ok')}, error={open_data.get('error', 'none')}")

    if not open_data.get("ok"):
        raise RuntimeError(f"DM チャンネルのオープンに失敗: {open_data.get('error')}")

    channel_id = open_data["channel"]["id"]
    print(f"DM チャンネル ID（取得）: {channel_id}")

    # ② メッセージを送信
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers=headers,
        json={"channel": channel_id, "blocks": blocks},
        timeout=10,
    )
    data = r.json()
    print(f"chat.postMessage: ok={data.get('ok')}, error={data.get('error', 'none')}")
    if not data.get("ok"):
        raise RuntimeError(f"Slack 投稿失敗: {data.get('error')}")
    print(f"✅ Slack DM 投稿完了！channel: {channel_id}")


def get_this_week_range():
    today        = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    this_monday  = today - timedelta(days=today.weekday())
    this_saturday = this_monday + timedelta(days=5)
    return this_monday, this_saturday


def run(week_start=None, week_end=None):
    if week_start is None or week_end is None:
        week_start, week_end = get_this_week_range()

    print(f"集計期間: {week_start.strftime('%Y-%m-%d')} 〜 {week_end.strftime('%Y-%m-%d')}")

    service    = build_calendar_service()
    raw_events = fetch_events(service, week_start, week_end)
    print(f"取得イベント数: {len(raw_events)}")

    events = filter_and_categorize(raw_events)
    print(f"集計対象: {len(events)} 件")

    blocks = build_blocks(events, week_start, week_end)
    post_dm(blocks)


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        ws = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=JST)
        we = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=JST)
        run(ws, we)
    else:
        run()
