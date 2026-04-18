# AI×セキュリティ ニュース日報

サイバーセキュリティ×AI分野のニュースを毎日自動収集・日本語要約して公開するサイト。

**完全無料構成:** GitHub Actions + Gemini API（無料枠）+ GitHub Pages + Google Apps Script

---

## セットアップ手順

### STEP 1: Gemini APIキーを取得

1. https://aistudio.google.com にアクセス（Googleアカウントでログイン）
2. 左メニュー「Get API key」→「Create API key」
3. 表示されたキー（`AIza...`）をコピーして保存

### STEP 2: GitHubアカウント作成 & リポジトリ作成

1. https://github.com でアカウント作成
2. 右上「+」→「New repository」
3. Repository name: `ai-security-news`
4. Public を選択（GitHub Pages無料公開に必要）
5. 「Create repository」

### STEP 3: ファイルをアップロード（Push）

Macのターミナルで以下を実行:

```bash
# Gitインストール確認（なければ自動でインストール案内が出る）
git --version

# プロジェクトフォルダに移動
cd ~/Downloads/ai-security-news   # ダウンロードしたフォルダのパス

# Git初期化 & Push
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/あなたのユーザー名/ai-security-news.git
git push -u origin main
```

### STEP 4: Gemini APIキーをGitHub Secretsに登録

1. GitHubリポジトリページ → 「Settings」タブ
2. 左メニュー「Secrets and variables」→「Actions」
3. 「New repository secret」
4. Name: `GEMINI_API_KEY`
5. Secret: STEPで取得したAPIキー（`AIza...`）を貼り付け
6. 「Add secret」

### STEP 5: GitHub Pages を有効化

1. リポジトリ「Settings」→ 左メニュー「Pages」
2. Branch: `main` / Folder: `/docs` を選択
3. 「Save」
4. 数分後に `https://あなたのID.github.io/ai-security-news` で公開される

### STEP 6: 初回手動実行でテスト

1. リポジトリ「Actions」タブ
2. 「Daily AI Security News」をクリック
3. 「Run workflow」→「Run workflow」
4. 緑チェックが付いたら成功 → GitHub Pagesにアクセスして確認

### STEP 7: Gmail自動送信を設定（GAS）

1. https://script.google.com にアクセス
2. 「新しいプロジェクト」
3. `gas/send_newsletter.gs` の内容をコピーして貼り付け
4. `RECIPIENT_EMAIL` と `SITE_URL` を自分のものに変更
5. 「トリガーを追加」→ `sendDailyNewsletter` / 毎日 / 午前8〜9時
6. 初回実行時にGmailへのアクセスを許可

---

## 収益化ロードマップ

| フェーズ | 内容 |
|---|---|
| Phase 1（今） | 無料公開・メール配信で読者獲得 |
| Phase 2 | Google AdSense申請（月1000PV目安） |
| Phase 3 | メール購読者向け有料プラン（Stripe連携） |
| Phase 4 | スポンサー・企業PR記事 |

---

## ソース信頼性ポリシー

**ティアA（引用自由）:** CISA, NIST, ENISA, Reuters, BBC
**ティアB（専門メディア）:** Krebs on Security, Dark Reading, SecurityWeek, Wired, Ars Technica
**ティアC（学術）:** arXiv（CC BYライセンス）

各記事の著作権は原著者・掲載メディアに帰属します。本サイトは要約・リンクのみ掲載します。
