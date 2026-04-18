// ================================================================
// send_newsletter.gs
// GitHub PagesのJSONを読んで毎朝Gmailでニュースレターを送信する
// 設定: トリガー → sendDailyNewsletter → 毎日 08:05（GAS側）
// ================================================================

// ===== 設定（ここだけ編集） =====
const RECIPIENT_EMAIL = "your@gmail.com";            // 受信するメールアドレス
const SITE_URL        = "https://あなたのID.github.io/ai-security-news"; // GitHub Pages URL
const JSON_URL        = SITE_URL + "/data/latest.json";
const SUBJECT_PREFIX  = "[AI×セキュリティ]";

// ================================================================
// メイン関数（毎日自動実行）
// ================================================================
function sendDailyNewsletter() {
  try {
    const data    = fetchLatestData();
    const today   = data.today || Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd");
    const articles = data.articles || [];

    if (articles.length === 0) {
      Logger.log("本日の記事なし。スキップ。");
      return;
    }

    const subject = `${SUBJECT_PREFIX} ${today} の注目ニュース（${articles.length}件）`;
    const htmlBody = buildEmailHTML(today, articles);

    GmailApp.sendEmail(
      RECIPIENT_EMAIL,
      subject,
      "このメールはHTMLメールです。HTMLに対応したメールクライアントでご確認ください。",
      { htmlBody: htmlBody, name: "AI×セキュリティ ニュース日報" }
    );

    Logger.log(`送信完了: ${subject}`);
  } catch (e) {
    Logger.log("エラー: " + e.toString());
    // エラー時は自分にアラートメール
    GmailApp.sendEmail(RECIPIENT_EMAIL, "[エラー] AI×セキュリティ ニュース日報", e.toString());
  }
}

// ================================================================
// GitHub PagesのJSONを取得
// ================================================================
function fetchLatestData() {
  const res = UrlFetchApp.fetch(JSON_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    throw new Error("JSON取得失敗: HTTP " + res.getResponseCode());
  }
  return JSON.parse(res.getContentText());
}

// ================================================================
// HTMLメール生成
// ================================================================
function buildEmailHTML(today, articles) {
  const importanceColor = { "高": "#E24B4A", "中": "#BA7517", "低": "#639922" };
  const tagColorMap = {
    "AI for Security": "#185FA5", "Security for AI": "#0F6E56",
    "脆弱性": "#993C1D", "脅威インテル": "#A32D2D",
    "規制・政策": "#3C3489", "研究・学術": "#3B6D11"
  };

  const articlesHTML = articles.map((a, i) => {
    const impColor = importanceColor[a.importance] || "#888780";
    const tags = (a.tags || []).map(t => {
      const c = tagColorMap[t] || "#5F5E5A";
      return `<span style="background:${c}22;color:${c};border:1px solid ${c}44;padding:2px 8px;border-radius:99px;font-size:11px;margin-right:4px">${t}</span>`;
    }).join("");

    return `
      <tr>
        <td style="padding:20px;border-bottom:1px solid #e5e3dc">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="font-size:11px;color:#888;padding-bottom:6px">
                <span style="background:#e6f1fb;color:#0c447c;padding:2px 7px;border-radius:99px;margin-right:6px">${tierLabel(a.source_tier)}</span>
                ${a.source_name}
                <span style="float:right;color:#aaa">${(a.published||"").substring(0,10)}</span>
              </td>
            </tr>
            <tr>
              <td style="padding-bottom:8px">
                <a href="${a.url}" style="font-size:16px;font-weight:600;color:#1a1a18;text-decoration:none;line-height:1.4">${a.title_ja}</a>
              </td>
            </tr>
            <tr>
              <td style="font-size:13px;color:#555;line-height:1.6;padding-bottom:10px">${a.summary_ja}</td>
            </tr>
            <tr>
              <td style="padding-bottom:6px">${tags}</td>
            </tr>
            <tr>
              <td style="font-size:11px;color:#aaa">
                重要度: <span style="color:${impColor};font-weight:500">${a.importance}</span>
                &nbsp;|&nbsp;
                出典: <a href="${a.url}" style="color:#185FA5">${a.source_name}</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>`;
  }).join("");

  return `
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:-apple-system,'Helvetica Neue',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f0;padding:20px 0">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">

        <!-- ヘッダー -->
        <tr><td style="background:#185FA5;padding:24px 28px;border-radius:10px 10px 0 0">
          <p style="margin:0;font-size:18px;font-weight:700;color:#fff">AI×セキュリティ ニュース日報</p>
          <p style="margin:4px 0 0;font-size:13px;color:#b5d4f4">${today} | 信頼できるソースのみ掲載</p>
        </td></tr>

        <!-- 記事一覧 -->
        <tr><td style="background:#fff;border-radius:0 0 10px 10px">
          <table width="100%" cellpadding="0" cellspacing="0">
            ${articlesHTML}
          </table>
        </td></tr>

        <!-- CTAフッター -->
        <tr><td style="padding:20px 0;text-align:center">
          <a href="${SITE_URL}" style="background:#185FA5;color:#fff;padding:10px 24px;border-radius:99px;font-size:13px;text-decoration:none;font-weight:500">Webサイトで全記事を読む</a>
        </td></tr>

        <!-- フッター -->
        <tr><td style="text-align:center;font-size:11px;color:#aaa;padding:0 0 20px">
          <p>各記事の著作権は原著者・掲載メディアに帰属します。</p>
          <p>Powered by Gemini API + GitHub Actions</p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>`;
}

function tierLabel(tier) {
  return { "A": "公的・大手", "B": "専門メディア", "C": "学術" }[tier] || tier;
}

// ================================================================
// テスト用：手動実行でメール送信テスト
// ================================================================
function testSend() {
  sendDailyNewsletter();
}
