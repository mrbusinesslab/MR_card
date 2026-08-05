import { createClient } from 'npm:@supabase/supabase-js@2';
import { TIPS } from '../_shared/tips.ts';

const ACCESS_TOKEN = Deno.env.get('LINE_CHANNEL_ACCESS_TOKEN')!;
const CRON_SECRET = Deno.env.get('CRON_SECRET') ?? '';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
);

const BRAND_CREAM = '#FBF8F1';
const BRAND_COFFEE = '#5c4a35';
const BRAND_TEXT = '#3a2f22';

function buildTipFlex(index: number, tip: (typeof TIPS)[number]) {
  return {
    type: 'flex',
    altText: `每週品牌小技巧：${tip.title}`,
    contents: {
      type: 'bubble',
      size: 'kilo',
      body: {
        type: 'box',
        layout: 'vertical',
        backgroundColor: BRAND_CREAM,
        paddingAll: '20px',
        spacing: 'md',
        contents: [
          {
            type: 'box',
            layout: 'horizontal',
            spacing: 'sm',
            contents: [
              {
                type: 'box',
                layout: 'vertical',
                width: '30px',
                height: '30px',
                cornerRadius: '15px',
                backgroundColor: BRAND_COFFEE,
                justifyContent: 'center',
                alignItems: 'center',
                contents: [{ type: 'text', text: tip.catLabel, size: 'xxs', color: BRAND_CREAM, weight: 'bold', align: 'center' }],
              },
              { type: 'text', text: '每週品牌小技巧', size: 'xs', color: BRAND_COFFEE, weight: 'bold', gravity: 'center' },
            ],
          },
          { type: 'text', text: tip.title, size: 'lg', weight: 'bold', color: BRAND_TEXT, wrap: true, margin: 'sm' },
          { type: 'separator', margin: 'md' },
          { type: 'text', text: tip.body, size: 'sm', color: BRAND_TEXT, wrap: true, margin: 'md' },
        ],
      },
      footer: {
        type: 'box',
        layout: 'vertical',
        backgroundColor: BRAND_CREAM,
        paddingAll: '12px',
        contents: [
          {
            type: 'box',
            layout: 'vertical',
            backgroundColor: BRAND_CREAM,
            borderColor: BRAND_COFFEE,
            borderWidth: 'medium',
            cornerRadius: '10px',
            paddingAll: '10px',
            action: {
              type: 'postback',
              label: '看完整內容',
              data: `action=tip_detail&idx=${index}`,
              displayText: '我想看完整內容',
            },
            contents: [{ type: 'text', text: '看完整內容', align: 'center', size: 'sm', weight: 'bold', color: BRAND_TEXT }],
          },
        ],
      },
    },
  };
}

async function broadcast(messages: unknown[]) {
  const res = await fetch('https://api.line.me/v2/bot/message/broadcast', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${ACCESS_TOKEN}`,
    },
    body: JSON.stringify({ messages: messages.slice(0, 5) }),
  });
  if (!res.ok) {
    const text = await res.text();
    console.error('LINE broadcast failed', res.status, text);
    throw new Error(`LINE broadcast failed: ${res.status} ${text}`);
  }
}

// 測試用：只推給單一個 userId，不會影響到其他好友
async function pushToUser(userId: string, messages: unknown[]) {
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${ACCESS_TOKEN}`,
    },
    body: JSON.stringify({ to: userId, messages: messages.slice(0, 5) }),
  });
  if (!res.ok) {
    const text = await res.text();
    console.error('LINE push failed', res.status, text);
    throw new Error(`LINE push failed: ${res.status} ${text}`);
  }
}

Deno.serve(async (req) => {
  const secret = req.headers.get('x-cron-secret') ?? '';
  if (!CRON_SECRET || secret !== CRON_SECRET) {
    return new Response('unauthorized', { status: 401 });
  }

  try {
    // 測試模式：request body 帶 { "test_user_id": "你的userId" } 時，
    // 只會推給這個人，而且不會更動 broadcast_state 的進度，不影響正式的每週輪播
    let testUserId: string | null = null;
    try {
      const body = await req.json();
      testUserId = body?.test_user_id ?? null;
    } catch {
      // 沒有帶 body 或不是合法 JSON，視為正式排程呼叫
    }

    const { data: state, error } = await supabase
      .from('broadcast_state')
      .select('*')
      .eq('id', 1)
      .maybeSingle();
    if (error) throw error;

    const currentIndex = state?.current_index ?? 0;
    const idx = currentIndex % TIPS.length;
    const tip = TIPS[idx];

    if (testUserId) {
      await pushToUser(testUserId, [buildTipFlex(idx, tip)]);
      return new Response(JSON.stringify({ ok: true, mode: 'test', sent_idx: idx, title: tip.title }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    await broadcast([buildTipFlex(idx, tip)]);

    const nextIndex = (currentIndex + 1) % TIPS.length;
    if (state) {
      await supabase
        .from('broadcast_state')
        .update({ current_index: nextIndex, updated_at: new Date().toISOString() })
        .eq('id', 1);
    } else {
      await supabase.from('broadcast_state').insert({ id: 1, current_index: nextIndex });
    }

    return new Response(JSON.stringify({ ok: true, mode: 'broadcast', sent_idx: idx, title: tip.title }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('weekly-tip-broadcast error', err);
    return new Response(JSON.stringify({ ok: false }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
});
