const ACCESS_TOKEN = Deno.env.get('LINE_CHANNEL_ACCESS_TOKEN')!;

export async function replyMessage(replyToken: string, messages: unknown[]) {
  const res = await fetch('https://api.line.me/v2/bot/message/reply', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${ACCESS_TOKEN}`,
    },
    // LINE reply API 一次最多 5 則訊息
    body: JSON.stringify({ replyToken, messages: messages.slice(0, 5) }),
  });

  if (!res.ok) {
    console.error('LINE reply failed', res.status, await res.text());
  }
}
