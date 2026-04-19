# AI×セキュリティ ニュース日報

サイバーセキュリティ×AI分野のニュースを毎日自動収集・日本語要約して公開するWebサイト。

**公開URL:** https://ayumu-thub.github.io/ai-security-news

---

## コンセプト

- **完全無料で動く** — GitHub Actions + Gemini API無料枠 + GitHub Pages
- **信頼できるソースのみ** — 公的機関・専門メディア・学術機関に厳選
- **AIが要約＋示唆を生成** — 読むだけでなく「何を学ぶべきか」まで提供
- **自動で毎日更新** — 一度設定すれば手動操作ゼロ
- **トレンドを可視化** — 何が今週急上昇しているかがひと目でわかる

---

## 現在の機能（v3）

### 収集・更新
- 1日1回（毎朝08:00 JST）GitHub Actionsが自動実行
- 1回あたり最大5件をピックアップ（注目トップ5）
- 過去90日分の記事を保持・アーカイブページ自動生成

### ソース（信頼性ティア制）

| ティア | ソース |
|---|---|
| A（公的機関） | CISA, NIST |
| B（専門メディア） | Krebs on Security, Dark Reading, SecurityWeek, The Hacker News, Bleeping Computer |
| B（Techメディア） | Wired Security, Ars Technica, MIT Tech Review |
| C（学術） | arXiv cs.CR, arXiv cs.AI |

### AI要約（Gemini 2.0 Flash Lite・無料枠）
各記事について以下を自動生成：
- 日本語タイトル・3〜4文の日本語要約
- **示唆・学び**（セキュリティ実務者視点での気づき）
- 重要度（高／中／低）＋判定理由
- 大項目タグ（7種）＋中項目タグ（固定リスト・最大3つ）

### タグ体系（事前定義・LLMはリスト外のタグ生成禁止）

| 大項目 | 中項目（抜粋） |
|---|---|
| 攻撃・脅威 | ランサムウェア, フィッシング, APT, マルウェア, DDoS, サプライチェーン攻撃 |
| 脆弱性 | ゼロデイ, CVE, エクスプロイト, パッチ未適用, 認証バイパス |
| AI×セキュリティ | プロンプトインジェクション, モデル汚染, 敵対的攻撃, LLMセキュリティ |
| AIリスク | ハルシネーション, バイアス・差別, プライバシー侵害, 安全性評価, アライメント |
| 規制・政策 | EU AI法, NIST, CISA勧告, 国内規制, コンプライアンス |
| インシデント | データ侵害, サービス停止, 情報漏洩, 金融被害 |
| ビジネス・技術動向 | 資金調達, 製品リリース, 市場トレンド, 研究・論文 |

### サイトUI（4タブ構成）
- **本日のニュース** — 最大5件、示唆・学び付き、全文公開・無料
- **人気記事** — 過去7日間のクリック数ランキング
- **アーカイブ** — 過去90日分、全記事誰でも無料閲覧
- **トレンド分析** — 急上昇トピック、大項目フィルター×中項目バー、重要度内訳

---

## ファイル構成

```
/
├── .github/workflows/daily.yml       # GitHub Actions（毎日08:00自動実行）
├── scripts/
│   ├── fetch_and_summarize.py        # RSS収集 + Gemini APIで要約・タグ付け
│   └── build_site.py                 # HTMLサイト生成（タブUI・ダッシュボード）
├── docs/                             # GitHub Pagesの公開先
│   ├── index.html                    # 自動生成トップページ
│   ├── archive/YYYY-MM-DD.html       # 日付別アーカイブ
│   └── data/latest.json              # 記事データ（JSON・90日分）
└── gas/
    └── send_newsletter.gs            # Gmail自動送信（Google Apps Script・オプション）
```

---

## セットアップ手順

### 必要なもの
- GitHubアカウント（無料）
- Googleアカウント（無料）
- Gemini APIキー（無料・aistudio.google.com で取得）

### 手順
1. Gemini APIキーを取得（aistudio.google.com）
2. このリポジトリをfork or clone
3. GitHub Secrets に `GEMINI_API_KEY` を登録
4. Settings → Pages → Branch: main / Folder: /docs → Save
5. Actions → Daily AI Security News → Run workflow で初回実行

---

## API使用量（無料枠の範囲内）

| サービス | 使用量 | 無料枠 |
|---|---|---|
| Gemini 2.0 Flash Lite | 1回/日・1APIコール | 1,500回/日 |
| GitHub Actions | 約5分/日 | 2,000分/月 |
| GitHub Pages | 静的HTML配信 | 完全無料 |

> **注意**: テスト実行を繰り返すとその日の無料枠を消費します。本番運用では毎朝1回のcron実行のみに留めてください。

---

## 著作権について

本サイトは各記事の**要約とリンクのみ**を掲載しています。原文・全文は掲載しておらず、著作権は原著者・掲載メディアに帰属します。
