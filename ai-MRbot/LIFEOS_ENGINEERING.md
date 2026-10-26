# Engineering secretary for the Xiaoruru demonstration

## Active seven-phase view

`progress_view: true` selects a seven-phase workflow: 預約／場勘、待報價、合約確認、備料準備、開始施工、完工收尾、驗收. Each phase has independent 未開始／進行中／已完成／不適用 status and a note. The segmented bar represents completed workflow phases, excluding 不適用 from the denominator; it does not measure physical construction completion. If every phase is skipped, the UI explicitly says that all phases are inapplicable rather than showing 100% completion.

Case overview and case detail now prioritize this workflow; tap a phase to change its state or edit its note. The expected finish date is a separate field. Note/date edits are previewed before saving. Notes detect concurrent edits; status changes update only their own phase. Both use backend tenant/membership checks and replay deduplication.

Apply the additive `lifeos_engineering_workflow.sql` once before deploying the extended gateway and Python view. Existing stages initialize seven-phase states, and linked task text/deadlines are copied into phase notes. Original task records remain intact. In this view, case-linked legacy tasks are omitted from the ordinary daily task display/reminders; legacy task menu commands open the phase view. New cases still use the guided case-creation flow. The older task-oriented view below remains available to profiles without `progress_view`.

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


### Completion dates and concise cards (2026-10-26)

Apply `lifeos_engineering_completion_dates.sql` after the seven-phase migration. It replaces only the authenticated workflow dispatcher; existing case data, notes, tasks and unknown historical dates are preserved. The existing gateway action allowlist remains unchanged.

New transitions to 已完成 record `completed_on` using the Taipei server date. Repeating the same state preserves the recorded date; reopening clears it. Completed phases can backfill/correct a past date with a preview and confirmation. A concurrent state change rejects a stale date edit. Webhook retries replay the prior result. Historical completed phases display 完成日期未記錄 until explicitly supplied; no dates are inferred.

The overview omits notes. Seven phase rows show status and, for completed phases, YYYY/MM/DD and elapsed calendar days in Taipei. Phase cards preview at most two lines/80 characters; 查看完整備註 retains access to all saved text. For workflow-enabled customer profiles only, buttons and quick replies use LINE postbacks with displayText exactly matching the visible label. A signature-checked customer webhook dispatches these in the same tenant/user context as typed commands. Other profiles retain their message actions.


### One-sentence progress reports

For the Xiaoruru engineering profile, the customer can send a full case name and a clear phase completion or start statement in their own words. A narrow deterministic parser previews the matched case, phase, state, and Taipei completion date. No database write occurs until the explicit 確認更新 button is tapped. The existing workflow status RPC uses expected_status to reject concurrent changes, and webhook event IDs to prevent duplicate writes. The reply shows the persisted phase count and next active phase. Negated, forecast, future, ambiguous, or unmatched reports do not update a phase. Existing stage cards and date editing remain available. Example: 陳先生浴室報價完成了.


### Four-field bookings and Google Maps

新增案場 now opens a single example card for 日期、案場名稱、預約工程、地點. Labeled lines (or comma-separated labels) are parsed deterministically; a supported one-sentence pattern is `10/30下午2點到3點，測試案場場勘，地點台中車站`. Missing fields are requested together with individual examples. Date-only entries explicitly preview as all-day; timed bookings require both start/end. Same-period times such as 下午2點到3點 inherit 下午. Invalid ranges are not saved.

The existing calendar draft/confirmation, overlap checks, tenant authorization and stable Google event ID are reused. No Google event or case is created before confirmation. After the confirmed calendar event and index are saved, create a new case if no accessible case has the exact name. Existing cases, phases, scope and address are preserved; each appointment retains its own location. If case creation is interrupted, confirmation retry reconciles the duplicate Google event and retries the case step. Booking is not a phase completion or expected-finish change.

Preview, conflict and saved cards include a Google Maps URI when a location is present; the Google event receives location. Case address cards also link to Maps. Links search the supplied address without silently geocoding or altering it. No Maps API key or new paid service is needed. Pending missing-field input expires after 20 minutes and cancels on navigation. Legacy MR profiles keep their existing case wizard.
