# AI×セキュリティ ニュース日報

サイバーセキュリティ×AI分野のニュースを毎日自動収集・日本語要約して公開するWebサイト。  
MSSP/CDCサービス設計者の観点で、AI for Security・Security for AI・SOC/CDC運用変化を重点的にカバーする。

**公開URL:** https://ayudle.github.io/ai-security-news

---

## コンセプト

- **完全無料で動く** — GitHub Actions + Gemini API無料枠 + GitHub Pages
- **CDC設計者の視点で厳選** — AI×セキュリティ、SOC/MDR/MSSP設計、Identity/Exposureに関連するニュースを優先
- **信頼できるソース定義** — 公的機関・専門メディア・ベンダー脅威インテリジェンスに厳選（広すぎるソースはAI×セキュリティの同時出現を要求）
- **AIが要約＋示唆を生成** — 読むだけでなく「CDC/SOCへの示唆」まで提供
- **人間の考察コラム** — 運営者によるMSSP/CDC設計に関する著者執筆コラムを掲載
- **自動で毎日更新** — 一度設定すれば手動操作ゼロ
- **トレンドを可視化** — 何が今週急上昇しているかがひと目でわかる

---

## 現在の機能（v3）

### 収集・更新
- 1日1回（毎朝08:00 JST）GitHub Actionsが自動実行
- 1回あたり最大10件をピックアップ（スコア・Tier・公開日の新しさで優先順位付け）
- 過去90日分の記事を保持・アーカイブページ自動生成

### ソース（信頼性ティア制）

| ティア | カテゴリ | ソース | strict_filter |
|---|---|---|---|
| A | 公的機関 | CISA, NIST | なし（セキュリティ記事を無条件収集） |
| A | 標準・コミュニティ | OWASP GenAI | なし |
| A | ベンダー公式 | Google Security Blog | なし |
| A | ベンダー脅威インテリジェンス | Palo Alto Unit 42 | なし |
| B | 専門メディア | Krebs on Security, Dark Reading, SecurityWeek, The Hacker News, Bleeping Computer | なし |
| B | AI×セキュリティ研究 | Embrace The Red | なし |
| B | Techメディア | Wired Security, Ars Technica | なし（セキュリティフィード限定） |
| C | AI研究・開発者ブログ | Simon Willison | **あり**（AI＋セキュリティの同時出現必須） |
| C | Techメディア | MIT Tech Review | **あり**（AI＋セキュリティの同時出現必須） |
| C | 学術・研究 | arXiv cs.CR | なし |

> `strict_filter=True` のソースは、AI関連キーワード＋セキュリティ/CDCキーワードの**両方が含まれる記事のみ**採用。

### フィルタリング設計

| キーワード群 | 役割 |
|---|---|
| `AI_KEYWORDS` | LLM/エージェント/プロンプト等・AI関連の一致を判定 |
| `SECURITY_KEYWORDS` | サイバー攻撃/脆弱性/侵害等・セキュリティ文脈の一致を判定 |
| `CDC_KEYWORDS` | SOC/MSSP/Identity/Exposure等・CDC設計文脈の一致を判定 |

収集判定：`has_ai OR has_sec OR has_cdc` のいずれかが True の場合に採用（strict_filter ソースは `has_ai AND (has_sec OR has_cdc)` が必要）。

### AI要約（Gemini 2.5 Flash）
各記事について以下を自動生成：
- 日本語タイトル・3〜4文の日本語要約
- **示唆・学び**（CISO/CDC設計者視点での気づき）
- 重要度（高／中／低）＋判定理由
- 大項目タグ（7種）＋中項目タグ（固定リスト・最大3つ）
- **CDC観点バッジ**（SOC運用変化, Identity/ITDR, Exposure管理, MDR/MSSP設計 等）
- **本日の示唆**（7セクション構造：今日の結論／攻撃側変化／防御側変化／Security for AI／AI for Security／CDC示唆／今日の問い）

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

### サイトUI（5タブ構成）
- **本日のニュース** — 最大10件、CDC観点バッジ・示唆・学び付き
- **アーカイブ** — 過去90日分、全記事誰でも無料閲覧
- **トレンド分析** — 急上昇トピック、ヒートマップ、重要度内訳
- **週次レポート** — 毎週月曜に自動生成
- **コラム** — 運営者による著者執筆の考察（LLM生成ではない）

### X投稿文生成（Phase 2: dry-run・スロット別）
- スコアリング（重要度・CDC関連度・ソースTier・AI関連度）で上位3件を選定
- 投稿スロット：morning 08:30 / noon 12:30 / evening 19:00（JST）
- `--all` で3本まとめて生成（daily.ymlから実行）、`--slot` でスロット単位1本生成（post_x_dry_run.ymlから実行）
- スロット別生成時は `docs/data/x_post_history.json` に `date + slot + article_id + text_hash` を記録（重複防止）
- **現在は dry-run のみ。本番投稿・X API連携は未実装（Phase 3で予定）**

```bash
# CLIの使い方
python scripts/generate_x_posts.py             # --all と同じ（3本一覧）
python scripts/generate_x_posts.py --all       # 3スロット分まとめて生成
python scripts/generate_x_posts.py --slot morning  # morning の1本だけ生成・履歴記録
```

---

## ファイル構成

```
/
├── .github/workflows/
│   ├── daily.yml                     # GitHub Actions（毎日08:00自動実行）
│   └── post_x_dry_run.yml            # X投稿文スロット別dry-run生成（1日3回）
├── scripts/
│   ├── fetch_and_summarize.py        # RSS収集 + Gemini APIで要約・タグ付け
│   ├── build_site.py                 # HTMLサイト生成（タブUI・ダッシュボード）
│   └── generate_x_posts.py          # X投稿文dry-run生成（--all / --slot 対応）
├── columns/                          # 著者執筆コラム（Markdown）
├── docs/                             # GitHub Pagesの公開先
│   ├── index.html                    # 自動生成トップページ
│   ├── article/                      # 記事個別ページ
│   ├── archive/YYYY-MM-DD.html       # 日付別アーカイブ
│   ├── columns/                      # コラム個別ページ
│   ├── weekly/                       # 週次レポート
│   └── data/
│       ├── latest.json               # 記事データ（JSON・90日分）
│       ├── x_posts_daily.json        # X投稿候補3本一覧（--all・日次更新）
│       ├── x_post_morning.json       # morning スロット投稿文（--slot morning）
│       ├── x_post_noon.json          # noon スロット投稿文（--slot noon）
│       ├── x_post_evening.json       # evening スロット投稿文（--slot evening）
│       └── x_post_history.json       # 投稿履歴（date/slot/article_id/text_hash）
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
| Gemini 2.5 Flash | 1回/日・1APIコール | 500回/日（無料枠） |
| GitHub Actions | 約5分/日 | 2,000分/月 |
| GitHub Pages | 静的HTML配信 | 完全無料 |

> **注意**: テスト実行を繰り返すとその日の無料枠を消費します。本番運用では毎朝1回のcron実行のみに留めてください。

---

## 著作権について

本サイトは各記事の**要約とリンクのみ**を掲載しています。原文・全文は掲載しておらず、著作権は原著者・掲載メディアに帰属します。
