import os
import logging
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

LINE_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
LINE_SECRET = os.environ["CHANNEL_SECRET"]
line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# ── デモ用：Q12（複数選択）のみ ──────────────────────────────
QUESTION = {
    "id": 12,
    "title": "注意・指摘の仕方は？",
    "help": "複数選択可：押すたびにON/OFF。最後に「✅ 完了」で確定。",
    "choices": [
        "ストレートに（わかりやすく）",
        "事実ベースで率直に（ストレート）",
        "ユーモアで和らげる"
    ]
}
# ユーザーごとの選択状態（簡易：メモリ保持）
PENDING = {}  # user_id -> set of selected labels

def make_quick_reply():
    items = [QuickReplyButton(action=MessageAction(label=c[:20], text=c))
             for c in QUESTION["choices"]]
    items.append(QuickReplyButton(action=MessageAction(label="✅ 完了", text="__DONE__")))
    items.append(QuickReplyButton(action=MessageAction(label="↩ クリア", text="__CLEAR__")))
    items.append(QuickReplyButton(action=MessageAction(label="⏭ スキップ", text="__SKIP__")))
    return QuickReply(items=items)

def send_question(user_id):
    text = f"Q{QUESTION['id']}. {QUESTION['title']}\n（{QUESTION['help']}）"
    line_bot_api.push_message(
        user_id,
        TextSendMessage(text=text, quick_reply=make_quick_reply())
    )

# ── Health check ─────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return "ok", 200

# ── Webhook ──────────────────────────────────────────────────
@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    logger.info("BODY: %s", body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.exception("Invalid signature")
        abort(401)
    except Exception:
        logger.exception("Unhandled error in callback")
    return "OK", 200

# ── メッセージ処理 ──────────────────────────────────────────
@handler.add(MessageEvent, message=TextMessage)
def on_message(event: MessageEvent):
    user_id = event.source.user_id or event.source.sender_id
    text = (event.message.text or "").strip()
    logger.info("Message from %s: %s", user_id, text)

    # スタート
    if text in ("開始", "start"):
        PENDING[user_id] = set()
        send_question(user_id)
        return

    # マルチ選択デモの制御
    if text == "__CLEAR__":
        sel = PENDING.get(user_id, set())
        sel.clear()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="選択をクリアしました。"))
        return

    if text == "__SKIP__":
        PENDING.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="この設問をスキップしました。"))
        return

    if text == "__DONE__":
        sel = list(PENDING.get(user_id, set()))
        PENDING.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"確定：{', '.join(sel) if sel else '（なし）'}"
        ))
        return

    # 通常の選択肢タップ（ON/OFF）
    if text in QUESTION["choices"]:
        sel = PENDING.setdefault(user_id, set())
        if text in sel:
            sel.remove(text)
            msg = f"解除：{text}\n現在：{', '.join(sel) if sel else '（なし）'}"
        else:
            sel.add(text)
            msg = f"選択：{text}\n現在：{', '.join(sel)}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # それ以外は簡易エコー（確認用）
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"OK: {text}"))
    except LineBotApiError:
        logger.exception("LineBotApiError")
        # 何も返せなくても落ちない
        pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

