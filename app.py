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

# ── 設問：5〜8択＋自由回答（min/maxで単一 or 複数に対応） ────────────────
QUESTION = {
    "id": 21,
    "title": "このキャラの注意・指摘の仕方は？",
    "help": "5〜8択＋自由回答。押すたびにON/OFF。必要数そろったら「✅ 完了」。",
    "choices": [
        "ストレートで簡潔に",
        "事実ベースで丁寧に",
        "ユーモアで和らげる",
        "共感から入る",
        "まず良い点を伝える",
        "根拠を示して説得",
        "例え話でわかりやすく",
        "相手のペースに合わせる"
    ],
    "min": 1,   # ← 単一選択なら 1,1 / 「ちょうど2つ」なら 2,2 など
    "max": 1
}

CMD_DONE  = "__DONE__"
CMD_CLEAR = "__CLEAR__"
CMD_SKIP  = "__SKIP__"
CMD_FREE  = "__FREE__"

# ユーザー状態（簡易メモリ）
# user_id -> {"selected": set[str], "await_free": bool}
STATE = {}

def make_quick_reply(user_id: str):
    sel = STATE.get(user_id, {}).get("selected", set())
    n, need = len(sel), QUESTION["max"]
    items = []
    for c in QUESTION["choices"]:
        items.append(QuickReplyButton(action=MessageAction(label=c[:20], text=c)))
    # 自由入力ボタン
    items.append(QuickReplyButton(action=MessageAction(label="✍ 自由入力", text=CMD_FREE)))
    # コントロール系
    items.append(QuickReplyButton(action=MessageAction(label=f"✅ 完了 ({n}/{need})", text=CMD_DONE)))
    items.append(QuickReplyButton(action=MessageAction(label="↩ クリア", text=CMD_CLEAR)))
    items.append(QuickReplyButton(action=MessageAction(label="⏭ スキップ", text=CMD_SKIP)))
    return QuickReply(items=items)

def send_question(user_id: str):
    text = f"Q{QUESTION['id']}. {QUESTION['title']}\n（{QUESTION['help']}）"
    line_bot_api.push_message(
        user_id,
        TextSendMessage(text=text, quick_reply=make_quick_reply(user_id))
    )

@app.get("/healthz")
def healthz():
    return "ok", 200

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

@handler.add(MessageEvent, message=TextMessage)
def on_message(event: MessageEvent):
    user_id = event.source.user_id or event.source.sender_id
    text = (event.message.text or "").strip()

    # start
    if text in ("開始", "start"):
        STATE[user_id] = {"selected": set(), "await_free": False}
        send_question(user_id)
        return

    # 自由入力待ちなら、次の発話をそのまま選択に追加
    st = STATE.get(user_id)
    if st and st.get("await_free") and text not in {CMD_DONE, CMD_CLEAR, CMD_SKIP, CMD_FREE}:
        sel = st["selected"]
        if len(sel) >= QUESTION["max"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"最大 {QUESTION['max']} 個までです。不要な選択を解除してから追加してください。", quick_reply=make_quick_reply(user_id))
            )
        else:
            label = f"自由:{text}"
            sel.add(label)
            st["await_free"] = False
            msg = f"自由入力を追加：{text}\n現在：{', '.join(sel)}（{len(sel)}/{QUESTION['max']}）"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg, quick_reply=make_quick_reply(user_id)))
        return

    # クリア
    if text == CMD_CLEAR:
        STATE.setdefault(user_id, {"selected": set(), "await_free": False})
        STATE[user_id]["selected"].clear()
        STATE[user_id]["await_free"] = False
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="選択をクリアしました。", quick_reply=make_quick_reply(user_id)))
        return

    # スキップ
    if text == CMD_SKIP:
        STATE.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="この設問をスキップしました。"))
        return

    # 自由入力モードに入る
    if text == CMD_FREE:
        STATE.setdefault(user_id, {"selected": set(), "await_free": False})
        STATE[user_id]["await_free"] = True
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="自由回答を1行で送ってください。"))
        return

    # 完了
    if text == CMD_DONE:
        sel = list(STATE.get(user_id, {}).get("selected", set()))
        mn, mx = QUESTION["min"], QUESTION["max"]
        if len(sel) < mn:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"あと {mn - len(sel)} 個選んでください。", quick_reply=make_quick_reply(user_id)))
            return
        if len(sel) > mx:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{mx} 個までです。解除してから完了してください。", quick_reply=make_quick_reply(user_id)))
            return
        # 確定
        STATE.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"確定：{', '.join(sel)}（{len(sel)}/{mx}）"))
        return

    # 通常の選択肢（ON/OFF）
    if text in QUESTION["choices"]:
        STATE.setdefault(user_id, {"selected": set(), "await_free": False})
        sel = STATE[user_id]["selected"]
        if text in sel:
            sel.remove(text)
            msg = f"解除：{text}\n現在：{', '.join(sel) if sel else '（なし）'}（{len(sel)}/{QUESTION['max']}）"
        else:
            if len(sel) >= QUESTION["max"]:
                msg = f"これ以上は選べません（最大 {QUESTION['max']} 個）。解除してから別の項目を選んでください。"
            else:
                sel.add(text)
                msg = f"選択：{text}\n現在：{', '.join(sel)}（{len(sel)}/{QUESTION['max']}）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg, quick_reply=make_quick_reply(user_id)))
        return

    # フォールバック（確認用）
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"OK: {text}"))
    except LineBotApiError:
        logger.exception("LineBotApiError")
        pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

