# AI×セキュリティ ニュース日報

サイバーセキュリティ×AI分野のニュースを毎日自動収集・日本語要約して公開するWebサイト。

---

## コンセプト

- **完全無料で動く**：GitHub Actions + Gemini API無料枠 + GitHub Pages
- **信頼できるソースのみ**：公的機関・専門メディア・学術機関に限定
- **AIが要約＋示唆を生成**：読むだけでなく「何を学ぶべきか」まで提供
- **自動で毎日更新**：一度設定すれば手動操作ゼロ

---

## 現在の要件

### 収集・更新
- 1日1回（毎朝08:00 JST）GitHub Actionsが自動実行
- 1回あたり最大5件をピックアップ（その日の注目トップ5）
- 5件に満たない日はそれ以下でもOK
- 過去90日分の記事を保持・アーカイブ

### ソース（信頼性重視・引用に耐えうる厳選）

| ティア | ソース | 理由 |
|---|---|---|
| A | CISA, NIST | 著作権フリー・政府機関 |
| B | Krebs on Security, Dark Reading, SecurityWeek, The Hacker News, Bleeping Computer | セキュリティ専門・RSS公開 |
| B | Wired Security, Ars Technica, MIT Tech Review | Tech専門メディア |
| C | arXiv cs.CR / cs.AI | CC BYライセンス・学術 |

### AI要約（Gemini 2.0 Flash Lite・無料枠）
- 日本語タイトル
- 3〜4文の日本語要約（背景・内容・影響の順）
- **示唆・学び**（セキュリティ実務者視点での気づき）
- 重要度（高／中／低）
- カテゴリタグ
- キーワード抽出

### サイト機能
- 本日のニュース（最大5件、全文公開・無料）
- 人気記事ランキング（閲覧数カウント）
- サイドバーのトレンドダッシュボード
  - カテゴリ分布バーチャート（過去30日）
  - 記事数の推移スパークライン（過去14日）
  - 頻出キーワードクラウド
  - 重要度の内訳
- 過去記事アーカイブ（全記事誰でも無料閲覧可）
- ダークモード対応

### スコープ
- **AI for Security**：AIを使った防御・検知・対応
- **Security for AI**：AIシステム自体への攻撃・保護
- どちらも対象

### 収益化（将来）
- 現時点では広告・有料機能なし
- 将来的にAdSense申請（コード上は枠だけ残してある）
- 将来的に有料購読も検討

---

## ファイル構成

```
/
├── .github/workflows/daily.yml     # GitHub Actions（毎日08:00自動実行）
├── scripts/
│   ├── fetch_and_summarize.py      # RSS収集 + Gemini APIで日本語要約
│   └── build_site.py               # HTMLサイト生成
├── docs/                           # GitHub Pagesの公開先
│   ├── index.html                  # 自動生成されるトップページ
│   ├── archive/YYYY-MM-DD.html     # 日付別アーカイブ
│   └── data/latest.json            # 記事データ（JSON）
└── gas/
    └── send_newsletter.gs          # Gmail自動送信（Google Apps Script）
```

---

## セットアップ手順

### 必要なもの
- GitHubアカウント（無料）
- Googleアカウント（無料）
- Gemini APIキー（無料）

### STEP 1：Gemini APIキーを取得
1. [aistudio.google.com](https://aistudio.google.com) にアクセス
2. 「Get API key」→「Create API key」
3. `AIza...` から始まるキーをメモ帳に保存

### STEP 2：GitHubリポジトリにpush
```bash
cd ~/Downloads/ai-security-news
git add -A
git commit -m "initial commit"
git push
```

### STEP 3：GitHub Secretsに登録
1. リポジトリ → Settings → Secrets and variables → Actions
2. 「New repository secret」
3. Name: `GEMINI_API_KEY` / Secret: APIキーを貼り付け

### STEP 4：GitHub Pagesを有効化
1. リポジトリ → Settings → Pages
2. Branch: `main` / Folder: `/docs` → Save

### STEP 5：初回テスト実行
1. Actions タブ → Daily AI Security News → Run workflow
2. 緑チェックが付いたら完成

### STEP 6：Gmail自動送信（オプション）
1. [script.google.com](https://script.google.com) で新規プロジェクト
2. `gas/send_newsletter.gs` の内容を貼り付け
3. `RECIPIENT_EMAIL` と `SITE_URL` を自分のものに変更
4. トリガーを毎日08:05に設定

---

## API使用量（無料枠の範囲内）

| サービス | 使用量 | 無料枠 |
|---|---|---|
| Gemini 2.0 Flash Lite | 1回/日・1APIコール | 1,500回/日 |
| GitHub Actions | 約5分/日 | 2,000分/月 |
| GitHub Pages | 静的HTML配信 | 完全無料 |
| Google Apps Script | 1回/日のメール送信 | 完全無料 |

> **注意**：テスト実行を繰り返すとその日の無料枠を消費します。
> 本番運用では毎朝1回のcron実行のみに留めてください。

---

## 各記事の著作権について

本サイトは各記事の**要約とリンクのみ**を掲載しています。
原文・全文は掲載しておらず、著作権は原著者・掲載メディアに帰属します。
