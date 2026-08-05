import { createClient } from 'npm:@supabase/supabase-js@2';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
);

const ACCESS_TOKEN = Deno.env.get('LINE_CHANNEL_ACCESS_TOKEN')!;
const CRON_SECRET = Deno.env.get('CRON_SECRET') ?? '';
const FOLLOWUP_DAYS = 3;

const REMINDER_TEXT =
  '之前的品牌診斷結果還在喔 🙋\n如果想更深入聊聊怎麼改善，隨時輸入「預約諮詢」，我們這邊看到會直接回覆你。';

async function pushMessage(userId: string, text: string): Promise<boolean> {
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${ACCESS_TOKEN}`,
    },
    body: JSON.stringify({ to: userId, messages: [{ type: 'text', text }] }),
  });
  if (!res.ok) {
    console.error('push failed', userId, res.status, await res.text());
    return false;
  }
  return true;
}

Deno.serve(async (req) => {
  // 用共用密鑰保護這個端點，避免被外部亂打導致亂發推播
  const secret = req.headers.get('x-cron-secret') ?? '';
  if (!CRON_SECRET || secret !== CRON_SECRET) {
    return new Response('unauthorized', { status: 401 });
  }

  const cutoff = new Date(Date.now() - FOLLOWUP_DAYS * 24 * 60 * 60 * 1000).toISOString();

  const { data, error } = await supabase
    .from('line_sessions')
    .select('user_id')
    .eq('state', 'DONE')
    .eq('consulted', false)
    .is('followup_sent_at', null)
    .lte('diagnosis_completed_at', cutoff);

  if (error) {
    console.error(error);
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }

  let sent = 0;
  for (const row of data ?? []) {
    const ok = await pushMessage(row.user_id, REMINDER_TEXT);
    if (ok) {
      await supabase
        .from('line_sessions')
        .update({ followup_sent_at: new Date().toISOString() })
        .eq('user_id', row.user_id);
      sent++;
    }
  }

  return new Response(JSON.stringify({ sent, candidates: (data ?? []).length }), {
    headers: { 'Content-Type': 'application/json' },
  });
});
