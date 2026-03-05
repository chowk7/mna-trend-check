import logging
import os
from datetime import date

from flask import Flask, jsonify, request, send_from_directory

from news_fetcher import DEFAULT_KEYWORDS, fetch_articles
from secret_manager import get_gemini_api_key
from summarizer import summarize_article

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")

_api_key: str | None = None


def get_api_key() -> str:
    global _api_key
    if _api_key is None:
        _api_key = get_gemini_api_key()
    return _api_key


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/news", methods=["POST"])
def api_news():
    body = request.get_json(force=True)

    try:
        date_from = date.fromisoformat(body["date_from"])
        date_to = date.fromisoformat(body["date_to"])
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"날짜 형식 오류: {e}"}), 400

    if date_from > date_to:
        return jsonify({"error": "시작 날짜가 종료 날짜보다 늦을 수 없습니다."}), 400

    max_results = int(body.get("max_results", 30))
    keywords = body.get("keywords", DEFAULT_KEYWORDS)

    articles = fetch_articles(date_from, date_to, max_results, keywords=keywords)

    # published_dt (datetime) is not JSON-serializable — strip it
    serializable = [
        {k: v for k, v in a.items() if k != "published_dt"}
        for a in articles
    ]
    return jsonify({"articles": serializable})


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    body = request.get_json(force=True)
    url = body.get("url", "")
    custom_format = body.get("custom_format", "")
    model = body.get("model", "gemini-2.0-flash")

    if not url:
        return jsonify({"error": "url이 필요합니다."}), 400

    try:
        api_key = get_api_key()
    except Exception as e:
        return jsonify({"error": f"API 키 로딩 실패: {e}"}), 500

    # summarize_article never raises — always returns a string
    summary = summarize_article(url, custom_format, api_key, model)
    return jsonify({"summary": summary})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
