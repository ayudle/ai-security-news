# Cyber Defense Notes

**脆弱性とサイバー防御運用の設計ノート**

脆弱性・CVE・悪用状況、脅威インテリジェンス、SOC/CDC、MDR/MSSP、Identity/ITDR、Exposure管理、AI for Security / Security for AIの最新動向を、実務者の視点で日本語に整理するナレッジ基盤です。

**公開URL:** https://ayudle.github.io/ai-security-news

## 収集の重点領域

- 脆弱性管理: CVE、ゼロデイ、KEV、エクスプロイト、パッチ、認証バイパス、RCE
- SOC/CDC運用: 検知・調査・対応、SIEM/SOAR、EDR/XDR/NDR、脅威ハンティング
- サービス設計: MDR/MSSP、エスカレーション、品質保証、経営報告
- Identity / Exposure: ITDR、PAM、非人間ID、CTEM、ASM、攻撃面管理
- AI×セキュリティ: AIの防御利用と、LLM・AIエージェントの防御

1日1回、最大15件を収集します。AI一般ニュースより、脆弱性対応と防御運用に直結する情報を優先します。

## 主な情報源

- 公的機関・標準: CISA、NIST、JPCERT/CC、OWASP GenAI
- 脆弱性研究: CERT/CC Vulnerability Notes、Google Project Zero、arXiv cs.CR
- 脅威インテリジェンス: Palo Alto Unit 42、Cisco Talos、Microsoft Security、CrowdStrike、Google Security Blog
- 専門メディア: Krebs on Security、Dark Reading、SecurityWeek、The Hacker News、Bleeping Computer

## 仕組み

1. GitHub ActionsがRSSを収集
2. 関連性と新しさで記事を選定
3. Gemini APIが日本語要約、タグ、SOC/CDC視点の示唆を生成
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
