import { createClient } from 'npm:@supabase/supabase-js@2';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
);

const DASHBOARD_KEY = Deno.env.get('DASHBOARD_KEY') ?? '';

const CATEGORY_LABELS: Record<string, string> = {
  trust: '信任建立',
  value: '價值傳遞',
  position: '品牌定位',
  digital: '數位曝光',
  referral: '口碑轉介',
};

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const key = url.searchParams.get('key') ?? '';
  if (!DASHBOARD_KEY || key !== DASHBOARD_KEY) {
    return new Response('unauthorized：請在網址後面加上 ?key=你設定的DASHBOARD_KEY', { status: 401 });
  }

  const [{ data: results, error: resultsErr }, { data: sessions, error: sessionsErr }] = await Promise.all([
    supabase.from('line_diagnosis_results').select('primary_category, created_at'),
    supabase.from('line_sessions').select('consulted, referral_code, referral_count'),
  ]);

  if (resultsErr || sessionsErr) {
    return new Response('資料讀取失敗：' + (resultsErr?.message ?? sessionsErr?.message), { status: 500 });
  }

  const totalCompleted = results?.length ?? 0;
  const totalUsers = sessions?.length ?? 0;
  const consultedCount = sessions?.filter((s) => s.consulted).length ?? 0;
  const conversionRate = totalCompleted > 0 ? Math.round((consultedCount / totalCompleted) * 100) : 0;

  const categoryCounts: Record<string, number> = {};
  for (const r of results ?? []) {
    if (!r.primary_category) continue;
    categoryCounts[r.primary_category] = (categoryCounts[r.primary_category] ?? 0) + 1;
  }
  const categoryLabelsOut = Object.keys(categoryCounts).map((c) => CATEGORY_LABELS[c] ?? c);
  const categoryValuesOut = Object.values(categoryCounts);

  const dailyCounts: Record<string, number> = {};
  const now = Date.now();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now - i * 86400000).toISOString().slice(0, 10);
    dailyCounts[d] = 0;
  }
  for (const r of results ?? []) {
    const d = (r.created_at as string).slice(0, 10);
    if (d in dailyCounts) dailyCounts[d]++;
  }
  const dailyLabels = Object.keys(dailyCounts);
  const dailyValues = Object.values(dailyCounts);

  const referralLeaders = (sessions ?? [])
    .filter((s) => (s.referral_count ?? 0) > 0)
    .sort((a, b) => (b.referral_count ?? 0) - (a.referral_count ?? 0))
    .slice(0, 5);

  const leaderRows =
    referralLeaders.length > 0
      ? referralLeaders.map((r) => `<tr><td>${r.referral_code}</td><td>${r.referral_count}</td></tr>`).join('')
      : '<tr><td colspan="2">目前還沒有轉介紀錄</td></tr>';

  const html = `<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>品牌診斷數據儀表板</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  body { font-family: -apple-system, "Segoe UI", "PingFang TC", sans-serif; background:#F7F1E6; color:#17140F; margin:0; padding:24px; }
  h1 { font-size:20px; margin-bottom:4px; }
  .sub { color:#5f5e5a; font-size:13px; margin-bottom:24px; }
  .cards { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:24px; }
  .card { background:#fff; border-radius:12px; padding:16px 20px; min-width:140px; box-shadow:0 1px 3px rgba(0,0,0,0.08); }
  .card .num { font-size:28px; font-weight:600; }
  .card .label { font-size:13px; color:#5f5e5a; margin-top:4px; }
  .chart-box { background:#fff; border-radius:12px; padding:20px; margin-bottom:24px; box-shadow:0 1px 3px rgba(0,0,0,0.08); max-width:680px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:8px; border-bottom:1px solid #eee; }
</style>
</head>
<body>
  <h1>品牌診斷數據儀表板</h1>
  <div class="sub">最後更新：${new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}</div>
  <div class="cards">
    <div class="card"><div class="num">${totalUsers}</div><div class="label">總互動人數</div></div>
    <div class="card"><div class="num">${totalCompleted}</div><div class="label">完成診斷數</div></div>
    <div class="card"><div class="num">${consultedCount}</div><div class="label">按下預約諮詢</div></div>
    <div class="card"><div class="num">${conversionRate}%</div><div class="label">諮詢轉換率</div></div>
  </div>
  <div class="chart-box"><canvas id="categoryChart" height="220"></canvas></div>
  <div class="chart-box"><canvas id="dailyChart" height="220"></canvas></div>
  <div class="chart-box">
    <h3 style="margin-top:0;font-size:15px;">轉介排行榜</h3>
    <table>
      <tr><th>推薦碼</th><th>成功推薦人數</th></tr>
      ${leaderRows}
    </table>
  </div>
<script>
  new Chart(document.getElementById('categoryChart'), {
    type: 'bar',
    data: {
      labels: ${JSON.stringify(categoryLabelsOut)},
      datasets: [{ label: '最大瓶頸次數', data: ${JSON.stringify(categoryValuesOut)}, backgroundColor: '#C9A961' }]
    },
    options: { plugins: { title: { display: true, text: '各分類成為「最大瓶頸」的次數' } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
  });
  new Chart(document.getElementById('dailyChart'), {
    type: 'line',
    data: {
      labels: ${JSON.stringify(dailyLabels)},
      datasets: [{ label: '每日完成診斷數', data: ${JSON.stringify(dailyValues)}, borderColor: '#17140F', backgroundColor: 'rgba(23,20,15,0.1)', fill: true, tension: 0.2 }]
    },
    options: { plugins: { title: { display: true, text: '近 14 天完成診斷趨勢' } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
  });
</script>
</body>
</html>`;

  return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
});
