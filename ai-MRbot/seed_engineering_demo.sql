-- Operator-run seed for the explicitly requested Xiaoruru engineering demo.
-- Additive and idempotent; never removes existing tasks or changes MR data.
begin;
do $seed$
declare owner_row lifeos_users%rowtype; entry jsonb; item jsonb; cid uuid; result jsonb;
 base_date date:=(now() at time zone 'Asia/Taipei')::date;
 fixtures jsonb:='[
 {"name":"陳先生浴室","location":"台中北區（虛構案場 A）","scope":"浴室壁面滲水檢查、防水修繕","stage":"待報價","tasks":[
  {"kind":"報價","title":"整理浴室防水報價並傳給客戶","day":1,"hour":17},
  {"kind":"報價","title":"追蹤報價回覆與施工意願","day":3,"hour":10},
  {"kind":"備料","title":"估算防水材料用量","day":2,"hour":12}]},
 {"name":"林小姐廚房","location":"台中北屯（虛構案場 B）","scope":"廚房冷熱水管更新，另有插座追加待確認","stage":"施工中","tasks":[
  {"kind":"備料","title":"購買止水閥與轉接頭，施工前帶齊","day":1,"hour":11},
  {"kind":"施工","title":"完成廚房配管並測試是否漏水","day":1,"hour":17},
  {"kind":"追加","title":"向客戶確認新增插座的追加費用","day":2,"hour":17}]},
 {"name":"張先生辦公室","location":"台中西屯（虛構案場 C）","scope":"辦公室牆面修繕與收尾驗收","stage":"待驗收","tasks":[
  {"kind":"驗收","title":"聯絡客戶確認驗收時間","day":1,"hour":16},
  {"kind":"追加","title":"修補踢腳板並整理完工照片","day":2,"hour":17},
  {"kind":"請款","title":"驗收後確認尾款三萬元是否收到（示範，需人工確認）","day":5,"hour":17}]}
 ]'::jsonb;
begin
 if (select count(*) from lifeos_users where tenant_id='xiaoruru' and shared_owner is null)<>1 then
  raise exception 'Expected one verified demo owner';
 end if;
 select * into owner_row from lifeos_users where tenant_id='xiaoruru' and shared_owner is null;
 -- All invited demo participants should see the same case-linked tasks.
 update lifeos_users set share_tasks=true where user_id=owner_row.user_id and tenant_id='xiaoruru';
 perform set_config('lifeos.tenant','xiaoruru',true);
 for entry in select value from jsonb_array_elements(fixtures) loop
  insert into lifeos_engineering_cases(tenant_id,user_id,name,location,scope,stage,demo)
   values('xiaoruru',owner_row.user_id,entry->>'name',entry->>'location',entry->>'scope',entry->>'stage',true)
   on conflict(tenant_id,user_id,name) do nothing returning id into cid;
  if cid is null then
   select id into cid from lifeos_engineering_cases where tenant_id='xiaoruru' and user_id=owner_row.user_id and name=entry->>'name' and demo;
   if cid is null then raise exception 'A real case uses this demo name; no overwrite'; end if;
  end if;
  for item in select value from jsonb_array_elements(entry->'tasks') loop
   result:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','xiaoruru','action','engineering_add_task',
    'user_id',owner_row.line_user_id,'case_id',cid,'kind',item->>'kind','title',item->>'title',
    'event_id','engineering-demo-v1:'||(entry->>'name')||':'||(item->>'title'),
    'due_at',((base_date+(item->>'day')::int)+(item->>'hour')::int*interval '1 hour') at time zone 'Asia/Taipei'));
   if result ? 'error' then raise exception 'Demo task failed: %',result; end if;
  end loop;
 end loop;
end $seed$;
commit;
