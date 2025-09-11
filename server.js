const express = require("express");
const line = require("@line/bot-sdk");

const config = {
  channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
  channelSecret: process.env.LINE_CHANNEL_SECRET,
};

const app = express();

app.post("/webhook", line.middleware(config), async (req, res) => {
  const events = req.body.events || [];
  await Promise.all(events.map(handleEvent));
  res.status(200).end();
});

const client = new line.Client(config);
async function handleEvent(ev) {
  if (ev.type !== "message" || ev.message.type !== "text") return;
  const text = ev.message.text.trim();
  const reply = `受け取り：「${text}」\n（建前）OK、まずは小さく試そう。`;
  return client.replyMessage(ev.replyToken, { type: "text", text: reply });
}

app.get("/", (_, res) => res.send("LINE webhook is running."));
const port = process.env.PORT || 3000;
app.listen(port, () => console.log("listening on " + port));
