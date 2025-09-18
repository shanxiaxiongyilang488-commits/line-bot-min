# 最小のLINE応答サーバー：どんなテキストにも「OK: <受け取った文>」で返事します
import os
import logging
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Render に入れた環境変数名（そのままでOK）
LINE_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
LINE_SECRET = os.environ["CHANNEL_SECRET"]

line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    logger.info("BODY: %s", body)   # ログに受信内容を出します

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.exception("Invalid signature")
        abort(401)
    except Exception:
        logger.exception("Unhandled error in callback")
        abort(500)
    return "OK", 200

@handler.add(MessageEvent, message=TextMessage)
def on_message(event: MessageEvent):
    text = (event.message.text or "").strip()
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"OK: {text}")
        )
    except LineBotApiError as e:
        logger.exception("LineBotApiError: %s %s", getattr(e, "status_code", "?"), getattr(e, "error", ""))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

