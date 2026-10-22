-- Uses the existing Supabase scheduler. Install the client key in Vault privately.
-- Never put its plaintext value in this file or reuse the original MR key.
select cron.schedule('lifeos-xiaoruru-daily-summary','0,15,30,45 1 * * *',$job$
  select net.http_post(
    url := 'https://mr-6c1r.onrender.com/clients/xiaoruru/lifeos/reminders',
    headers := jsonb_build_object('Content-Type','application/json','Authorization',
      'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name='lifeos_xiaoruru_cron_key')),
    body := '{}'::jsonb,
    timeout_milliseconds := 20000
  );
$job$);

select cron.schedule('lifeos-xiaoruru-test-reminder','* * * * *',$job$
  select net.http_post(
    url := 'https://mr-6c1r.onrender.com/clients/xiaoruru/lifeos/test-reminders',
    headers := jsonb_build_object('Content-Type','application/json','Authorization',
      'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name='lifeos_xiaoruru_cron_key')),
    body := '{}'::jsonb,
    timeout_milliseconds := 20000
  ) where exists (
    select 1 from public.lifeos_test_reminders
    where tenant_id='xiaoruru' and state<>'sent' and due_at<=now() and due_at>now()-interval '15 minutes'
  );
$job$);
