"""
Meeting Summary Bot - v7
・メインDM：サマリー（合計・カテゴリ別バー・週別内訳）
・スレッド：カテゴリごとに分割して全会議リストを返信
  （Slack の50ブロック上限対策）
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

MY_EMAIL      = os.environ["MY_EMAIL"]
SLACK_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
SLACK_USER_ID = os.environ.get("SLACK_USER_ID", "U041CPB9927")
CALENDAR_ID   = os.environ.get("CALENDAR_ID", "primary")
PERIOD_TYPE   = os.environ.get("PERIOD_TYPE", "weekly")
JST           = timezone(timedelta(hours=9))

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
SLACK_MAX_BLOCKS = 48  # Slack上限50のうち余裕を持って48


# ──────────────────────────────────────────────
# 期間計算
# ──────────────────────────────────────────────

def get_this_week_range():
    today         = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    this_monday   = today - timedelta(days=today.weekday())
    this_saturday = this_monday + timedelta(days=5)
    return this_monday, this_saturday


def get_this_month_range():
    today       = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1)
    return month_start, month_end


def get_period_range(period_type, custom_start=None, custom_end=None):
    if period_type == "monthly":
        return get_this_month_range()
    elif period_type == "custom":
        if not custom_start or not custom_end:
            raise ValueError("custom 指定時は custom_start と custom_end が必要です")
        ws = datetime.fromisoformat(custom_start).replace(tzinfo=JST)
        we = datetime.fromisoformat(custom_end).replace(tzinfo=JST)
        return ws, we
    else:
        return get_this_week_range()


# ──────────────────────────────────────────────
# Google Calendar
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# フィルタリング・分類
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# フォーマット
# ──────────────────────────────────────────────

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


def period_label(period_type, week_start, week_end):
    end_day = week_end - timedelta(days=1)
    if period_type == "monthly":
        return (
            "📅 今月の会議実績レポート",
            f"{week_start.year}年{week_start.month}月（{week_start.month}/1〜{end_day.month}/{end_day.day}）"
        )
    elif period_type == "custom":
        return (
            "📅 会議実績レポート",
            f"{week_start.month}/{week_start.day}〜{end_day.month}/{end_day.day}"
        )
    else:
        fri = week_end - timedelta(days=1)
        return (
            "📅 今週の会議実績レポート",
            f"{week_start.month}/{week_start.day}(月)〜{fri.month}/{fri.day}(金)"
        )


# ──────────────────────────────────────────────
# Slack メッセージ構築
# ──────────────────────────────────────────────

def build_summary_blocks(events, period_type, week_start, week_end):
    """メインDM用：サマリーのみ"""
    totals = defaultdict(lambda: {"minutes": 0, "count": 0})
    for ev in events:
        totals[ev["category"]]["minutes"] += ev["minutes"]
        totals[ev["category"]]["count"]   += 1

    total_min   = sum(v["minutes"] for v in totals.values())
    total_count = sum(v["count"]   for v in totals.values())
    header_title, date_range = period_label(period_type, week_start, week_end)

    blocks = []
    blocks.append({"type": "header", "text": {"type": "plain_text", "text": header_title, "emoji": True}})
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

    # 週別内訳（月次のみ）
    if period_type == "monthly":
        by_week = defaultdict(list)
        for ev in events:
            d = datetime.strptime(ev["date"], "%Y-%m-%d")
            monday = d - timedelta(days=d.weekday())
            by_week[monday.strftime("%Y-%m-%d")].append(ev)

        week_lines = ["*📆 週別内訳*"]
        for monday_str in sorted(by_week):
            wk_evs = by_week[monday_str]
            wk_min = sum(e["minutes"] for e in wk_evs)
            monday = datetime.strptime(monday_str, "%Y-%m-%d")
            friday = monday + timedelta(days=4)
            week_lines.append(
                f"　*{monday.month}/{monday.day}〜{friday.month}/{friday.day}*　"
                f"{fmt_time(wk_min)}　{len(wk_evs)}件"
            )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(week_lines)}})
        blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "💬 全会議リストはこのメッセージのスレッドをご確認ください"}],
    })

    return blocks


def build_cat_detail_text(events, cat):
    """1カテゴリ分の全会議リストをテキストで生成（スレッド投稿用）"""
    by_cat = defaultdict(list)
    for ev in sorted(events, key=lambda x: (x["date"], x["time"])):
        by_cat[ev["category"]].append(ev)

    evs = by_cat[cat]
    if not evs:
        return None

    cat_min = sum(e["minutes"] for e in evs)
    lines   = [f"{CAT_EMOJI[cat]} *{cat}*　_{fmt_time(cat_min)} / {len(evs)}件_"]

    # 1メッセージあたりの行数制限（Slack上限対策）
    MAX_LINES = 40
    for ev in evs[:MAX_LINES]:
        lines.append(
            f"　• {weekday_ja(ev['date'])} {ev['time']}　{ev['title']}　_{fmt_time(ev['minutes'])}_"
        )
    if len(evs) > MAX_LINES:
        lines.append(f"　_…他 {len(evs) - MAX_LINES} 件_")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Slack 投稿
# ──────────────────────────────────────────────

def open_dm_channel():
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"}
    print(f"Slack ユーザー ID: {SLACK_USER_ID}")

    open_resp = requests.post(
        "https://slack.com/api/conversations.open",
        headers=headers,
        json={"users": SLACK_USER_ID},
        timeout=10,
    )
    open_data = open_resp.json()
    print(f"conversations.open: ok={open_data.get('ok')}, error={open_data.get('error', 'none')}")

    if not open_data.get("ok"):
        raise RuntimeError(f"DM チャンネルのオープンに失敗: {open_data.get('error')}")

    return open_data["channel"]["id"]


def post_message(channel_id, blocks=None, text=None, thread_ts=None):
    """ブロックまたはテキストでメッセージを投稿"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"}
    payload = {"channel": channel_id}
    if blocks:
        payload["blocks"] = blocks
    if text:
        payload["text"] = text
    if thread_ts:
        payload["thread_ts"] = thread_ts

    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers=headers,
        json=payload,
        timeout=10,
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack 投稿失敗: {data.get('error')}")
    return data["ts"]


def post_dm_with_thread(events, period_type, week_start, week_end):
    channel_id = open_dm_channel()
    print(f"DM チャンネル ID: {channel_id}")

    # ① メインメッセージ（サマリー）
    summary_blocks = build_summary_blocks(events, period_type, week_start, week_end)
    main_ts = post_message(channel_id, blocks=summary_blocks)
    print(f"✅ メインメッセージ投稿完了")

    # ② スレッドに全会議リストをカテゴリ別に返信
    # 最初のスレッドメッセージ（ヘッダー）
    post_message(
        channel_id,
        text="*📋 全会議リスト（承諾済み・複数人）*",
        thread_ts=main_ts
    )

    for cat in CATEGORIES:
        cat_text = build_cat_detail_text(events, cat)
        if cat_text:
            post_message(channel_id, text=cat_text, thread_ts=main_ts)
            print(f"✅ スレッド返信完了: {cat}")

    # フッター
    post_message(
        channel_id,
        text="※ accepted + 複数人のみ集計。移動・ブロック・workingLocation は除外。",
        thread_ts=main_ts
    )
    print("✅ 全投稿完了！")


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────

def run(period_type=None, custom_start=None, custom_end=None):
    period_type = period_type or PERIOD_TYPE
    week_start, week_end = get_period_range(period_type, custom_start, custom_end)

    print(f"期間タイプ: {period_type}")
    print(f"集計期間: {week_start.strftime('%Y-%m-%d')} 〜 {week_end.strftime('%Y-%m-%d')}")

    service    = build_calendar_service()
    raw_events = fetch_events(service, week_start, week_end)
    print(f"取得イベント数: {len(raw_events)}")

    events = filter_and_categorize(raw_events)
    print(f"集計対象: {len(events)} 件")

    post_dm_with_thread(events, period_type, week_start, week_end)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        pt = sys.argv[1]
        cs = sys.argv[2] if len(sys.argv) > 2 else None
        ce = sys.argv[3] if len(sys.argv) > 3 else None
        run(pt, cs, ce)
    else:
        run()
