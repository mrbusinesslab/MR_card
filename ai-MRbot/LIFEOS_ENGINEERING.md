# Engineering secretary for the Xiaoruru demonstration

The `industry: engineering` setting in `clients/xiaoruru.json` enables an engineering home screen, persisted cases, progress updates, case-linked tasks, and case calendar searches. The existing MR profile remains general. The LINE account display name/avatar is managed separately in LINE Official Account Manager.

## Usage

- `生活助理` / `工程秘書`: engineering home.
- `案件總覽`: case cards; `案件 陳先生`: find a unique case by name.
- `工程待辦`, `報價追蹤`, `待驗收`: filtered views.
- `建立案件 案名｜地點｜工項`: preview and confirm a new case.
- `工程進度 案名｜待驗收`: preview and confirm progress. Stages: 待場勘、待報價、待確認、待施工、施工中、待驗收、已結案.
- `工程事項 案名｜備料｜明天下午五點前買材料`: preview and confirm one linked task. Types: 報價、備料、施工、追加、驗收、請款、其他.
- Use normal task cards to complete/cancel/postpone. Linked tasks are ordinary Life OS tasks and appear in opt-in daily summaries.
- Calendar events require start/end times; no beauty F/B default duration. Engineering calendar categories: 場勘 blue, 施工 orange, 驗收 green, 會議 purple.

## Installation and isolation

Apply `lifeos_engineering.sql` once, deploy `lifeos_gateway/index.ts` (the existing custom-key authentication stays enabled), then deploy this Python/profile update. The additive RPC validates the key-selected tenant and enrolled original LINE identity, uses existing task sharing rules, and namespaces webhook deduplication records. New tables have RLS enabled, no anon/authenticated access; the RPC is security invoker and service_role only.

Run `seed_engineering_demo.sql` only for the explicitly requested demonstration. It creates three clearly marked fictional cases and nine tasks without deleting existing data or enabling notifications. It enables task sharing only for this demo owner so invited demo participants can use the same case board. Google demo events are separate no-attendee/no-reminder events in the Xiaoruru calendar and are indexed for name-based rescheduling/cancellation.

## Boundaries

Progress is manually updated. No inventory accounting, automatic bank reconciliation, photo storage, routing, or multi-worker dispatch is provided. `請款` is a reminder category, not a payment ledger. No push messages are sent during installation.

## Compact LINE cards

The engineering home has four main choices. Case overview uses one bubble per case with the current stage, next task, and deadline; addresses and scope live in a separate details view. Task lists show four clickable task rows per page, and operations open only after selecting a row. Completed, postponed, newly created and progress-updated items receive short acknowledgements with a return action.

New-case and new-task buttons now ask one field at a time before explicit confirmation. These unsaved prompts are request-profile scoped, expire after 20 minutes, and clear on process restart. They do not overwrite task/calendar drafts. Replayed webhook steps reuse their reply instead of advancing twice. Existing text commands remain supported.

The protected `engineering-check` endpoint accepts `validate_cards: true` to submit the home, overview, task list, detail and progress picker to LINE's validation endpoint without sending messages.

## Validation

Run Python unit tests, `node --test tests/test_gateway.mjs`, and `node tests/check_engineering.mjs` after `npm ci --prefix tests`. The database suite checks case persistence, webhook retries, cross-tenant access/mutation rejection, shared access and revocation, ordinary task linkage, and backend-only privileges. The same SQL assertions can run on production with rollback.
