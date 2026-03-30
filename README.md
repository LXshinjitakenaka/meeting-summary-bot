# Meeting Summary Bot

毎週金曜 21:00 に「今週の会議実績」を自分の Slack DM へ自動投稿するボット。

---

## 投稿イメージ

```
📅 今週の会議実績レポート
3/23(月)〜3/28(金)

合計　23h 25m / 41件

🏢 社内定例  ██████████░░░░░░  9h 45m  18件  42%
🤝 社外      ██████░░░░░░░░░░  6h 00m  10件  26%
👤 1on1      █████░░░░░░░░░░░  5h 25m  13件  23%
📢 全社      ██░░░░░░░░░░░░░░  2h 15m   3件   9%

📆 曜日別内訳
  3/23(月)  7h 30m  14件
  3/24(火)  2h 00m   3件
  ...

📋 全会議リスト（承諾済み・複数人）
🏢 社内定例  9h 45m / 18件
  • 3/23(月) 08:30  かな・いた・たけ定例  30m
  • 3/23(月) 09:00  Daily-Checkin  30m
  ...
```

---

## セットアップ手順

### STEP 1｜Google Cloud — サービスアカウント作成（約 30 分）

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. プロジェクトを選択（なければ新規作成）
3. **「APIとサービス」→「ライブラリ」** で `Google Calendar API` を検索 → 有効化
4. **「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」**
5. 名前（例: `meeting-summary-bot`）を入力して作成
6. 作成後、**「キー」タブ → 「鍵を追加」→「JSON」** でキーをダウンロード
7. ダウンロードした JSON の**中身全体**をコピーしておく（STEP 3 で使用）

**カレンダーへの共有設定:**
1. Google カレンダー → 自分のカレンダーの「…」→「設定と共有」
2. 「特定のユーザーとの共有」にサービスアカウントのメール（`...@...iam.gserviceaccount.com`）を追加
3. 権限: **「予定の閲覧（すべての予定の詳細）」**

---

### STEP 2｜Slack App 作成（約 15 分）

1. [Slack API](https://api.slack.com/apps) → **「Create New App」→「From scratch」**
2. アプリ名（例: `Meeting Bot`）とワークスペースを選択
3. 左メニュー **「OAuth & Permissions」**
4. **「Scopes」→「Bot Token Scopes」** に以下を追加:
   - `chat:write`
   - `im:write`
   - `users:read`
   - `users:read.email`
5. **「Install to Workspace」** → 許可
6. **Bot User OAuth Token**（`xoxb-...`）をコピー

**自分の DM チャンネル ID を調べる:**
1. Slack で自分の名前をクリック → DM を開く
2. ブラウザの URL を確認: `https://app.slack.com/client/T.../D...`
3. `D` で始まる部分が Channel ID（例: `D01234ABCDE`）

---

### STEP 3｜GitHub Secrets を設定（約 10 分）

リポジトリの **「Settings」→「Secrets and variables」→「Actions」→「New repository secret」**

| Secret 名 | 値 |
|-----------|-----|
| `MY_EMAIL` | あなたの Google アカウントのメールアドレス |
| `SLACK_BOT_TOKEN` | `xoxb-...` で始まる Bot Token |
| `SLACK_MY_CHANNEL_ID` | `D` で始まる DM チャンネル ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | STEP 1 でダウンロードした JSON の中身全体 |
| `CALENDAR_ID` | `primary`（デフォルト） |

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
2. **「Weekly Meeting Summary (Friday Night)」** を選択
3. **「Run workflow」** → 期間を入力して実行
   - `week_start`: `2026-03-23`
   - `week_end`: `2026-03-28`
4. Slack DM に届けば成功 🎉

以後、毎週金曜 21:00 JST に今週分が自動投稿されます。

---

## カスタマイズ

### 投稿時刻を変更

`.github/workflows/weekly_meeting_summary.yml` の cron を変更:

```yaml
# 金曜 20:00 JST = UTC 11:00
- cron: "0 11 * * 5"
```

[crontab.guru](https://crontab.guru/) で確認できます。

### 1on1 のキーワードを追加

`meeting_summary.py` の `CATEGORY_KEYWORDS["1on1"]` に追記してください。

### ローカルテスト

```bash
pip install -r requirements.txt

# credentials.json = サービスアカウント JSON をリネームして同ディレクトリに置く
export MY_EMAIL="your@email.com"
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_MY_CHANNEL_ID="D01234ABCDE"

python meeting_summary.py 2026-03-23 2026-03-28
```
