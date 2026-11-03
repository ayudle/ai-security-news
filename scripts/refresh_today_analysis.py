"""当日分の既存記事に、新しい業務・攻撃メタデータだけを追加する手動処理。"""
import json
import os
import tempfile
from datetime import datetime

from fetch_and_summarize import JST, OUTPUT_PATH, summarize_with_gemini


def main():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    with open(OUTPUT_PATH, encoding="utf-8") as file:
        data = json.load(file)
    days = [day for day in data.get("history", []) if day.get("date") == today]
    if len(days) != 1 or data.get("today") != today:
        raise ValueError("本日の記事データが一意に見つかりません。更新しません")
    articles = days[0].get("articles", [])
    if not articles or len(articles) > 15:
        raise ValueError("本日の記事件数が不正です。更新しません")
    if all(isinstance(article.get("attack"), dict) for article in articles):
        print("本日の分析情報は追加済みです。APIを呼ばずに終了します")
        return

    enriched, _ = summarize_with_gemini(articles)
    if len(enriched) != len(articles) or [a.get("id") for a in enriched] != [a.get("id") for a in articles]:
        raise ValueError("記事IDが一致しません。既存データを保持します")
    if not all(a.get("business", {}).get("evidence") is not None and
               isinstance(a.get("attack"), dict) for a in enriched):
        raise ValueError("分析結果が不足しています。既存データを保持します")
    if not any(a["attack"].get("evidence_status") != "不明" for a in enriched):
        raise ValueError("攻撃・インシデントの根拠付き分類が得られませんでした。既存データを保持します")

    updates = {article["id"]: {"business": result["business"], "attack": result["attack"]}
               for article, result in zip(articles, enriched)}
    for article in articles:
        article.update(updates[article["id"]])
    for article in data.get("articles", []):
        if article.get("id") in updates:
            article.update(updates[article["id"]])
    data["updated"] = datetime.now(JST).isoformat()

    directory = os.path.dirname(OUTPUT_PATH)
    fd, temporary = tempfile.mkstemp(prefix="refresh-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, OUTPUT_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"本日の既存記事 {len(articles)} 件へ分析情報を追加しました")


if __name__ == "__main__":
    main()
