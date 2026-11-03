# Cyber Defense Notes

**脆弱性診断・脆弱性管理・AIエージェントの業務インプット**

脆弱性・CVE・悪用状況、脅威インテリジェンス、SOC/CDC、MDR/MSSP、Identity/ITDR、Exposure管理、AI for Security / Security for AIの最新動向を、実務者の視点で日本語に整理するナレッジ基盤です。

**公開URL:** https://ayudle.github.io/ai-security-news

## 収集の重点領域

- 脆弱性管理: CVE、ゼロデイ、KEV、エクスプロイト、パッチ、認証バイパス、RCE
- SOC/CDC運用: 検知・調査・対応、SIEM/SOAR、EDR/XDR/NDR、脅威ハンティング
- サービス設計: MDR/MSSP、エスカレーション、品質保証、経営報告
- Identity / Exposure: ITDR、PAM、非人間ID、CTEM、ASM、攻撃面管理
- AI×セキュリティ: AIの防御利用と、LLM・AIエージェントの防御
- 診断技術・評価: AI診断ハーネス、ソースコード/動的診断の検知性能、正解データとベンチマーク、修正案の安全性と機能維持、再診断

1日1回、最大15件を収集します。脆弱性管理ライフサイクル、ソースコード/ブラックボックス診断、診断技術・評価、AIエージェント、企業インシデント、政策・地政学を対象に、国内情報と一次情報を加点します。関連情報が少ない日は水増ししません。

診断技術・評価は「対象となる診断やセキュリティ課題」と「ハーネス・評価・修正検証の方法」が併記された記事を加点します。単にAIやベンチマークに触れた記事は加点しません。arXiv cs.CRとcs.SEは7日間の更新を確認し、cs.SEからはこの領域に一致する論文だけを採用します。過去に掲載した同じURLは再掲載しません。研究論文は最大2,000文字のRSS抜粋をGeminiへ渡し、評価方法・数値・限界を要約できるようにします。

この領域の例: [診断ハーネスの設計](https://thehackernews.com/2026/10/the-harness-is-hard-part-of-agentic.html)（ベンダー寄稿）、[MetaVulのハーネス最適化](https://arxiv.org/abs/2610.40721)、[RiskyPyの安全性・機能性評価](https://arxiv.org/abs/2610.40735)。サイトの「診断技術・評価」ページと記事検索の同名テーマから、該当する過去記事も探せます。

追加情報（悪用状況、対象製品、対応緊急度、日本企業との関連、ライフサイクル、診断種別）はGeminiのJSON Schemaで形式を固定し、根拠のない情報は「不明」にします。短いRSS抜粋による評価なので、対応判断は元の公表資料で確認してください。過去記事は再生成課金せず「未評価」と表示します。

履歴は日数で削除せず保持します。画面は共通のライトテーマ（`docs/assets/site.css`）を使用します。

## 主な情報源

- 公的機関・標準: CISA、NIST、JPCERT/CC、OWASP GenAI
- 国内: JVN、IPA注意喚起、JPCERT/CC分析ブログ、Security NEXT
- 診断・開発: PortSwigger Research、GitHub Security
- 脆弱性・診断研究: CERT/CC Vulnerability Notes、Google Project Zero、arXiv cs.CR / cs.SE
- 脅威インテリジェンス: Palo Alto Unit 42、Cisco Talos、Microsoft Security、CrowdStrike、Google Security Blog
- 専門メディア: Krebs on Security、Dark Reading、SecurityWeek、The Hacker News、Bleeping Computer

## 仕組み

1. GitHub ActionsがRSSを収集
2. 関連性と新しさで記事を選定
3. Gemini APIが日本語要約、タグ、根拠付き業務情報、実務上の示唆を1回のバッチで生成
4. `scripts/build_site.py`が静的HTMLを生成
5. `docs/`をGitHub Pagesで公開

SNS APIへの自動投稿やSNS認証情報は使用しません。

## セットアップ

1. Google AI StudioでGemini APIキーを取得
2. GitHub Secretsに`GEMINI_API_KEY`を登録
3. Settings → Pagesで`main` / `docs` folderを選択
4. Actions → Daily AI Security Newsを実行

APIキーはコードや設定ファイルに書かず、GitHub Secretsからのみ渡します。

## ファイル構成

```text
.
├── .github/workflows/
│   ├── daily.yml
│   ├── weekly.yml
│   └── rebuild.yml
├── scripts/
│   ├── fetch_and_summarize.py
│   ├── build_site.py
│   └── generate_weekly.py
├── columns/
└── docs/
    ├── index.html
    ├── article/
    ├── archive/
    ├── weekly/
    └── data/
```

## 運用上の注意

- 要約・タグ・示唆はLLMの自動生成です。重要な判断には必ず元記事を確認してください。
- Geminiへ送信するのは公開RSSのタイトル、概要、URLです。社内情報や個人情報を入力しないでください。
- 公開リポジトリのため、コミット用メールはGitHubの`noreply`アドレスを使ってください。

## 著作権

本サイトは各記事の要約とリンクのみを掲載します。原文の著作権は原著者・掲載メディアに帰属します。
