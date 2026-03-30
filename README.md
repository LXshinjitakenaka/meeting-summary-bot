# Meeting Summary Bot

毎週金曜 21:00 に「今週の会議実績」を自分の Slack DM へ自動投稿するボット。
月次・カスタム期間にも対応。全会議リストはスレッドで確認できます。

---

## 投稿イメージ

**メインDM（サマリー）**
```
📅 今週の会議実績レポート
3/23(月)〜3/28(金)

合計　23h 25m / 41件

🏢 社内定例  ██████████░░░░░░  9h 45m  18件  42%
🤝 社外      ██████░░░░░░░░░░  6h 00m  10件  26%
👤 1on1      █████░░░░░░░░░░░  5h 25m  13件  23%
📢 全社      ██░░░░░░░░░░░░░░  2h 15m   3件   9%

🗓 曜日別内訳
  3/23(月)  7h 30m  14件
  3/24(火)  2h 00m   3件
  ...

💬 全会議リストはこのメッセージのスレッドをご確認ください
```

**スレッドを開くと（カテゴリ別・全会議一覧）**
```
📋 全会議リスト（承諾済み・複数人）

🏢 社内定例  9h 45m / 18件
  • 3/23(月) 08:30  かな・いた・たけ定例  30m
  • 3/23(月) 09:00  Daily-Checkin  30m
  ...

🤝 社外  6h 00m / 10件
  ...
```

---

## 対応する期間タイプ

| period_type | 内容 | 自動実行 |
|-------------|------|---------|
| `weekly` | 今週月〜金 | 毎週金曜 21:00 JST |
| `monthly` | 今月1日〜末日（週別内訳つき） | 毎月最終日 21:00 JST |
| `custom` | 任意の開始日・終了日を指定 | 手動のみ |

---

## セットアップ手順

### STEP 1｜Google Cloud — サービスアカウント作成（約30分）

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. **「APIとサービス」→「ライブラリ」** で `Google Calendar API` を検索 → 有効化
3. **「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」**
4. 名前（例: `meeting-summary-bot`）を入力して作成
5. 作成後、**「キー」タブ → 「鍵を追加」→「JSON」** でキーをダウンロード
6. ダウンロードした JSON の**中身全体**をコピーしておく（STEP 3 で使用）

**カレンダーへの共有設定:**
1. Google カレンダー → 自分のカレンダーの「…」→「設定と共有」
2. 「特定のユーザーとの共有」にサービスアカウントのメール（`...@...iam.gserviceaccount.com`）を追加
3. 権限: **「予定の閲覧（すべての予定の詳細）」**

---

### STEP 2｜Slack App 作成（約15分）

1. [Slack API](https://api.slack.com/apps) → **「Create New App」→「From scratch」**
2. アプリ名（例: `Meeting Summary Bot`）とワークスペースを選択
3. 左メニュー **「OAuth & Permissions」→「Bot Token Scopes」** に以下を追加:

| スコープ | 用途 |
|---------|------|
| `chat:write` | メッセージを送信する |
| `im:write` | DM チャンネルを開く |
| `im:read` | DM チャンネルを読む |
| `im:history` | DM の履歴にアクセスする |
| `users:read` | ユーザー情報を取得する |
| `users:read.email` | メールアドレスでユーザーを検索する |

4. **「Install to Workspace」** → 許可
5. **Bot User OAuth Token**（`xoxb-...`）をコピー

**自分の Slack ユーザー ID を調べる:**
1. Slack で自分のプロフィールを開く
2. 「…」→「メンバー ID をコピー」→ `U` で始まる文字列

**自分の DM チャンネル ID を調べる:**
1. ブラウザ版 Slack（app.slack.com）で自分の名前をクリックして DM を開く
2. URL の `D` で始まる部分（例: `D01234ABCDE`）をコピー

---

### STEP 3｜GitHub Secrets を設定（約10分）

リポジトリの **「Settings」→「Secrets and variables」→「Actions」→「New repository secret」**

| Secret 名 | 値 |
|-----------|-----|
| `MY_EMAIL` | あなたの Google カレンダーのメールアドレス |
| `SLACK_BOT_TOKEN` | `xoxb-...` で始まる Bot Token |
| `SLACK_USER_ID` | `U` で始まる Slack ユーザー ID |
| `SLACK_MY_CHANNEL_ID` | `D` で始まる DM チャンネル ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | STEP 1 でダウンロードした JSON の中身全体 |
| `CALENDAR_ID` | 自分のメールアドレス（例: `yourname@company.com`） |

---

### STEP 4｜リポジトリにプッシュ

```bash
git init
git add .
git commit -m "Add meeting summary bot"
git remote add origin https://github.com/YOUR_NAME/meeting-summary-bot.git
git push -u origin main
```

---

### STEP 5｜動作確認（手動実行）

1. GitHub → **「Actions」タブ**
2. **「Meeting Summary Bot」** を選択
3. **「Run workflow」** → 期間タイプと日付を入力して実行

| やりたいこと | `period_type` | 追加入力 |
|------------|--------------|---------|
| 今週分を今すぐ確認 | `weekly` | なし |
| 今月分をまとめて確認 | `monthly` | なし |
| 特定期間を確認 | `custom` | 開始日・終了日（YYYY-MM-DD） |

4. Slack DM に届いたら成功 🎉

---

## 集計ルール

- **承諾済み（accepted）かつ複数人参加**のイベントのみ対象
- 以下は除外：移動・ブロック・病院・workingLocation・outOfOffice
- カテゴリ分類：
  - **全社**：Daily-Checkin、生徒総会、lx_all メーリングリスト含むもの
  - **1on1**：タイトルに「1on1」「Shinji /」など特定キーワードを含むもの
  - **社外**：@lxdesign.me 以外の参加者がいるもの
  - **社内定例**：上記以外

## % の計算式

```
カテゴリの合計分数 ÷ 全体の合計分数 × 100（四捨五入）
```

---

## カスタマイズ

### 投稿時刻を変更

`.github/workflows/weekly_meeting_summary.yml` の cron を変更:

```yaml
# 例: 金曜 20:00 JST = UTC 11:00
- cron: "0 11 * * 5"
```

### 除外タイトルを追加

`meeting_summary.py` の `SKIP_TITLES` に追記:

```python
SKIP_TITLES = {
    "移動", "ブロック",
    "追加したいタイトル",  # ← ここに追加
}
```

### 1on1 キーワードを追加

`meeting_summary.py` の `CATEGORY_KEYWORDS["1on1"]` に追記:

```python
"1on1": [
    "1on1", "Shinji /",
    "追加したいキーワード",  # ← ここに追加
],
```

### ローカルテスト

```bash
pip install -r requirements.txt

# credentials.json = サービスアカウント JSON をリネームして同ディレクトリに置く
export MY_EMAIL="your@email.com"
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_USER_ID="U01234ABCDE"
export CALENDAR_ID="your@email.com"

# 週次
python meeting_summary.py weekly

# 月次
python meeting_summary.py monthly

# 任意期間
python meeting_summary.py custom 2026-03-01 2026-04-01
```
