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

select cron.schedule('lifeos-test-reminder','* * * * *', $job$
  select net.http_post(
    url := 'https://mr-6c1r.onrender.com/lifeos/test-reminders',
    headers := jsonb_build_object('Content-Type','application/json','Authorization',
      'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name='lifeos_cron_key')),
    body := '{}'::jsonb,
    timeout_milliseconds := 20000
  ) where exists (
    select 1 from public.lifeos_test_reminders
    where state<>'sent' and due_at<=now() and due_at>now()-interval '15 minutes'
  );
$job$);
