import { handleEvent } from './handler.ts';
import { verifySignature } from './verify.ts';

const CHANNEL_SECRET = Deno.env.get('LINE_CHANNEL_SECRET') ?? '';

Deno.serve(async (req) => {
  if (req.method !== 'POST') {
    return new Response('ok', { status: 200 });
  }

  const rawBody = await req.text();
  const signature = req.headers.get('x-line-signature') ?? '';

  const valid = await verifySignature(rawBody, signature, CHANNEL_SECRET);
  if (!valid) {
    return new Response('invalid signature', { status: 401 });
  }

  let body: { events?: any[] };
  try {
    body = JSON.parse(rawBody);
  } catch {
    return new Response('bad request', { status: 400 });
  }

  const events = body.events ?? [];

  // 先回 200 給 LINE 避免逾時重送，事件處理用 Promise.all 平行跑完
  await Promise.all(
    events.map((event) =>
      handleEvent(event).catch((err) => {
        console.error('handleEvent error', err);
      }),
    ),
  );

  return new Response('ok', { status: 200 });
});
