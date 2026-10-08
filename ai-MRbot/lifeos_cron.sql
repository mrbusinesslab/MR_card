-- Existing Supabase scheduler; no additional Render cron service.
-- Secret is installed into Vault separately and is never committed.
select cron.schedule('lifeos-daily-summary','0,15,30,45 1 * * *', $job$
  select net.http_post(
    url := 'https://mr-6c1r.onrender.com/lifeos/reminders',
    headers := jsonb_build_object('Content-Type','application/json','Authorization',
      'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name='lifeos_cron_key')),
    body := '{}'::jsonb,
    timeout_milliseconds := 20000
  );
$job$);
