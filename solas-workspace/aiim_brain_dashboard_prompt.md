# Aureon DGX Brain Control Center — Builder Prompt
# Sent when builder is ready. DO NOT MODIFY WITHOUT REVIEW.

Upgrade the existing "High Impact Features" page into the Aureon DGX Brain Control Center.
Do NOT delete, rename, or break any existing page, entity, function, record, AIIM system, RSI system, DGX integration, assistant profile, ontology entity, customer memory, governance record, replay record, or patent component. Keep the 88 High-Impact Features catalog as a collapsed section at the BOTTOM of the page.

---
## PAGE HEADER

Title: "Aureon DGX Brain Control Center"
Subtitle (small text below): "Private operational intelligence · Governed reasoning · Verifiable action · Controlled recursive improvement"
Top-right: last refreshed timestamp + "Refresh" button + admin-only "Run Health Check" button (calls checkAureonSystemHealth backend function, shows result inline).

---
## SECTION 1 — TOP STATUS BAR (14 live stat tiles in 2 rows of 7)

Row 1:
1. DGX Status — from DGXNode entity, heartbeatStatus field. Show ONLINE (green), DEGRADED (amber), OFFLINE (red). If no DGXNode records: "Not configured"
2. Models Online — count of AureonModelRegistry where isActive=true. If 0: "No models registered"
3. Observations Today — count of AIIMObservation where created_date >= today midnight. If 0: "No data yet"
4. Active World Objects — count of AIIMWorldObject records. If entity missing: "Awaiting first run"
5. Ontology Relationships — count of OntologyLink records. If entity missing: "Awaiting first run"
6. Current Conflicts — count of AIIMFactClaim where supportState=CONFLICTED. If 0: show 0 with green dot
7. Reasoning Jobs Running — count of AIIMReasoningJob where status=processing or pending. If 0: "Idle"

Row 2:
8. Actions Awaiting Approval — count of AIIMGovernanceDecision where decision=PENDING_APPROVAL or REQUIRE_APPROVAL
9. Verified Outcomes Today — count of AIIMOutcome where created_date >= today midnight and verificationStrength > 0
10. Replay Pass Rate — (count AIIMReplayRun where stateDivergence=false) / (total AIIMReplayRun count). Show as percentage. If no records: "No replays yet"
11. RSI Experiments Active — count of AIIMImprovementExperiment where status NOT IN (REJECTED, ROLLED_BACK, RELEASED)
12. Queue Depth — count of DGXJobQueue where statusV3 IN (CREATED, DISPATCH_PENDING, DISPATCHED, PROCESSING)
13. Avg Response Latency — average avgResponseMs from DGXNode. Show in ms. If no data: "Not calibrated"
14. Est. Cloud Cost Avoided — count of AureonInvocationLedger where modelUsed CONTAINS "DGX" * $0.002. Show as "$X.XX saved today". If no data: "Awaiting first DGX run"

---
## SECTION 2 — BRAIN PIPELINE VISUALIZATION

Horizontal pipeline with 12 connected stage nodes. Each stage has: stage name, status dot, job count badge, last activity time (relative). Clicking any stage opens a side drawer with the last 10 records from that stage's entity.

Stages:
1. Observe — AIIMObservation (status: active if records in last 1h)
2. Resolve Identity — AIIMWorldObject (identityStatus field)
3. Build Ontology — OntologyLink (count of links created today)
4. Retrieve Memory — CustomerMemory + AIIMContextFrame
5. Reason — AIIMReasoningJob
6. Critic Review — AIIMReasoningOutput (criticResult field not null)
7. AIIM Governance — AIIMGovernanceDecision
8. Human Approval — AIIMHumanOverride (newDecision=PENDING)
9. Execute — AIIMAction (status=completed today)
10. Measure Outcome — AIIMOutcome
11. Replay — AIIMReplayRecord + AIIMReplayRun
12. RSI Learn — RSILearningEvent + AIIMImprovementExperiment

Stage color: green = activity in last 1h, amber = activity in last 24h but not 1h, grey = no activity.

---
## SECTION 3 — LIVE BRAIN ACTIVITY FEED

Real-time activity feed (auto-refresh every 30s). Pull from: AIIMObservation, AIIMReasoningJob, AIIMAssistantRun, AIIMGovernanceDecision, DGXJobQueue, AIIMAction, AIIMOutcome, RSILearningEvent. Sort by created_date descending. Show last 25 events.

Each row shows:
- Time (relative: "2 min ago")
- Event type icon (circle-dot for observation, brain for reasoning, shield for governance, check for action, chart for outcome)
- Short description: e.g. "Customer message observed", "Reasoning job dispatched", "AIIM decision: REQUIRE_APPROVAL", "Action executed: update_quote_status"
- Dealer badge
- Status badge (color-coded by governance result or status)
- Expandable row: click to see full record details (NO raw chain-of-thought, NO private payloads — show only: reasoning summary, evidence used, agents used, model used, governance decision, confidence score)

If no records: show empty state "Brain has not yet received any events. Configure DGX and trigger an observation to begin."

---
## SECTION 4 — MEMORY SYSTEM PANEL

8 memory cards in a 4x2 grid:

1. Working Memory — AIIMContextFrame count, avg expiresAt countdown, last created
2. Episodic Memory — AIIMEpisode count, last created, dealerId coverage
3. Semantic Memory — AIIMFactClaim count, supportState breakdown (SUPPORTED/CONFLICTED/STALE counts), avg confidenceScore
4. Customer Memory — CustomerMemory count, avg freshness (last updated), stale count (not updated in 30d)
5. Equipment Memory — Equipment entity count + EquipmentRecord count, last inspection date
6. Procedural Memory — AIIMLearningPattern count by patternTier, promoted count
7. Governance Memory — AIIMGovernanceDecision total count, ALLOW vs BLOCK ratio (last 30d)
8. Replay Memory — AIIMReplayRecord count, AIIMReplayRun count, stateDivergence count

Each card: title, record count (large), freshness indicator (last updated), provenance avg (if available), a small status badge (Healthy/Stale/Empty). Card color: green border if data fresh (<24h), amber if stale (>24h), grey if empty.

---
## SECTION 5 — STORAGE ARCHITECTURE PANEL

2-column layout. Left: storage system cards. Right: configuration checklist.

LEFT — Storage system tiles (show connected/disconnected honestly):
1. Base44 Operational DB — always CONNECTED. Show total entity record counts (sum of key entities: Equipment, Customer, Quote, AIIMObservation, AIIMAction, AIIMGovernanceDecision)
2. Vector Memory Store — show "Not configured — add DGX_API_URL to Base44 Secrets". If DGX_API_URL secret is set, show CONNECTED.
3. Ontology Graph — show count of AIIMWorldObject + OntologyLink. Storage: Base44 DB (current), "Dedicated graph engine: not configured"
4. Event & Replay Store — count of AIIMObservation + AIIMReplayRecord + DGXJobQueue. Storage: Base44 DB.
5. Object Storage — show "Not configured — MinIO/S3 endpoint required". 
6. Model Registry — count of AureonModelRegistry records. Show "Populated" if > 0, else "Empty"
7. Evaluation Dataset Store — show "Not configured — required for RSI calibration"
8. Redis Cache — show "Not configured — required for idempotency keys and nonce storage"

RIGHT — Admin Setup Checklist (checkmarks for each completed item):
☐/☑ DGX_API_URL configured (Base44 Secret)
☐/☑ DGX_API_KEY configured
☐/☑ DGX_WEBHOOK_SECRET configured
☐/☑ DGX_MAA_PUBLIC_KEY configured
☐/☑ DGX_MAA_KEY_ID configured
☐/☑ AureonModelRegistry populated (> 0 records)
☐/☑ AureonRoutingPolicy populated (> 0 records)
☐/☑ First AIIMObservation created
☐/☑ First AIIMReasoningJob created
☐/☑ First AIIMGovernanceDecision created
☐/☑ First AIIMAction completed
☐/☑ First AIIMOutcome recorded
☐/☑ First AIIMReplayRun completed
☐/☑ First RSILearningEvent recorded

Check each item by querying the relevant entity count. For secrets: check if DGXNode records exist with isActive=true as a proxy. Show progress bar: X of 14 configured.

---
## SECTION 6 — MODEL OPERATIONS PANEL

Table of all AureonModelRegistry records. Admin only.

Columns: Model Key | Model Name | Role | Provider | Status (isActive badge) | Latency Target | Priority | Customer Facing | Actions

Actions column (admin only): "Disable" toggle | "Test" button (sends test ping) | "View Runs" (filters AureonInvocationLedger by modelUsed)

Below table: Routing Policy sub-table from AureonRoutingPolicy. Columns: Task Type | Preferred Model | Local First badge | Cloud Fallback badge | Max Latency | Notes

---
## SECTION 7 — ONTOLOGY BRAIN PANEL

3 stat tiles: Active World Objects | Ontology Links | Unresolved Conflicts

Below: 2-column layout.
Left: World Object type breakdown — group AIIMWorldObject by ontologyType, show bar chart (each type a horizontal bar with count).
Right: Recent ontology changes — last 10 OntologyLink records created or updated. Columns: From Object | Predicate | To Object | Support State | Created.

Below: Claim Quality tiles in a row:
- Supported Facts (AIIMFactClaim supportState=SUPPORTED count)
- Inferred Claims (epistemicType=INFERRED count)  
- Predictions (epistemicType=PREDICTED count)
- Conflicted (supportState=CONFLICTED count — amber if > 0)
- Stale (freshnessState=STALE count — amber if > 0)
- Unknown (supportState=UNKNOWN count)

If AIIMFactClaim entity has no records: show "No fact claims yet. Claims are created by aureonCreateFactClaim when observations are processed."

---
## SECTION 8 — REASONING OPERATIONS PANEL

Table of last 20 AIIMReasoningJob records. Columns: Job ID (8 chars) | Type | Dealer | Status badge | Model Route | Agents | Context Frame | Created | Latency | Result

Expandable row detail: show AIIMReasoningOutput linked by requestId — display: reasoningSummary, missingEvidence, assumptions, criticResult summary, confidence. NO raw chain-of-thought.

Filters: Status | Dealer | Date range | Model

---
## SECTION 9 — AIIM GOVERNANCE PANEL

Two sub-sections:

Top: Decision breakdown tiles (6 tiles in a row, each showing count for last 7d):
ALLOW (green) | ALLOW_PREAUTHORIZED (teal) | DOWNGRADE (blue) | REQUIRE_APPROVAL (amber) | BLOCK (red) | QUARANTINE (dark red)

Bottom: Recent decisions table — last 20 AIIMGovernanceDecision records. Columns: Decision badge | Action Name | Entity Type | Dealer | Governance AR | Governance PR | Consequence Score | Reversibility | Decided At | Human Approval Status

---
## SECTION 10 — APPROVAL CENTER

Card list of all AIIMGovernanceDecision where decision IN (REQUIRE_APPROVAL, PENDING_APPROVAL). Sorted by created_date desc.

Each card shows:
- Action name (bold)
- Entity type + Entity ID (8 chars)
- Dealer badge
- Requested by
- Consequence score bar
- Reversibility badge (green=reversible, red=irreversible)
- Evidence completeness bar
- Agents used
- AIIM decision badge
- Expiration countdown (amber if < 2h remaining)
- Approve button (green) | Reject button (red) | Request Evidence button | Assign Reviewer button

Approve creates AIIMHumanOverride with newDecision=APPROVED. Reject creates with newDecision=REJECTED and prompts for reason.

If no pending approvals: green banner "No actions awaiting approval"

---
## SECTION 11 — RSI LABORATORY

Full experiment pipeline display. One card per AIIMImprovementExperiment record.

Card shows: Experiment ID | Problem Statement | Hypothesis | Affected Task | Status badge (color by stage) | Effect Size | Confidence Interval | Owner | Expires At

Expanded view: baseline metrics, treatment description, replay result, shadow result, canary result, policy impact, rollback trigger, safety metrics.

Stage advancement: "Advance Stage" button (admin only). Stages in order: OBSERVATION → HYPOTHESIS → REPLAY → SHADOW → CANARY → HUMAN_REVIEW → APPROVED → RELEASED → MONITORING. ROLLED_BACK and REJECTED are terminal.

"New Experiment" button (admin only): opens modal with fields for all AIIMImprovementExperiment required fields.

Pattern tier section below: group AIIMLearningPattern by patternTier. Show count per tier. Highlight any UX_BEHAVIOR or USER_PREFERENCE patterns that have been incorrectly classified as OPERATIONAL_GOLDEN with a warning badge.

---
## SECTION 12 — DGX JOB QUEUE PANEL

Table of DGXJobQueue records. Default filter: statusV3 NOT IN (COMPLETED, EXPIRED). Show all statuses toggle.

Columns: Job ID (8 chars) | Task Type | Dealer | Status badge (color-coded) | Attempt Count | Created | Age | Latency | Error (truncated) | Actions

Status colors: CREATED=grey, DISPATCHED=blue, PROCESSING=amber spinning, COMPLETED=green, FAILED_RETRYABLE=orange, FAILED_FINAL=red, DEAD_LETTERED=dark red, EXPIRED=grey strikethrough

Actions (admin only): Retry | Cancel | Move to Dead Letter | Inspect (shows payloadHash, idempotencyKey, schemaVersion — never raw payload)

Auto-refresh every 30s.

---
## SECTION 13 — SECURITY PANEL

6 stat tiles in a row (all count last 24h):
- HMAC Failures (SecurityAuditLog eventType=dgx_result_rejected)
- MAA Failures (SecurityAuditLog eventType=maa_verification_failed)  
- Cross-Dealer Blocks (SecurityAuditLog result=DENY with reason containing "cross-dealer")
- Governance Blocks (AIIMGovernanceDecision decision=BLOCK last 24h)
- Nonce Replays (SecurityAuditLog reason containing "Nonce reuse")
- Circuit Breaker Events (AureonInvocationLedger where circuitOpen=true)

Below: SecurityAuditLog table — last 50 records. Columns: Time | Event Type | Dealer | Result badge (ALLOW green/DENY red) | Reason (truncated)

---
## SECTION 14 — DATA QUALITY PANEL

Diagnostic tiles showing data health issues. Each tile: issue name, count, "Fix" or "Preview" button. Fixes must show preview before executing.

Issues to detect:
- AIIMObservation records missing dealerId
- AIIMAction records missing idempotencyKey
- AIIMFactClaim records with confidenceScore > 1 (normalization error)
- AIIMGovernanceDecision records with metricSemanticsVersion < 2 (need migration)
- DGXJobQueue records with statusV3=FAILED_FINAL older than 7d (dead letter candidates)
- AIIMReplayRun records with stateDivergence=true (need review)
- AIIMContextFrame records that are expired but immutableAfterUse=false (cleanup candidates)
- AIIMLearningPattern records with patternTier=OPERATIONAL_GOLDEN but replayPassed=false (invalid promotion)

"Run Migration" button: calls aureonMigrateMetrics backend function for each entity type. Shows dry-run results before executing.

---
## SECTION 15 — HIGH IMPACT FEATURES CATALOG (collapsed by default)

Keep the existing 88 High-Impact Features section exactly as it is, inside a collapsible accordion panel at the bottom. Accordion header: "High Impact Features Catalog (88 features)" with expand/collapse toggle.

Inside, add a readiness status column to each feature card showing one of: Designed | Data Model Ready | Backend Wired | DGX Wired | AIIM Governed | Shadow Mode | Production | Monitoring

A feature is "Production" only when: backend function exists AND required data flows AND governance is wired AND at least one real run record exists.

---
## STYLE NOTES

- Dark background consistent with existing app theme
- Section headers: bold, left-aligned, with a thin left accent bar
- All "Not configured" and "No data yet" states must be clearly distinct from real zero values
- Loading states: skeleton loaders for all data-driven sections
- Responsive: sections stack vertically on smaller screens
- Never show secrets, raw authentication tokens, raw payloads, or private chain-of-thought
- Admin-only controls must be hidden for non-admin users, not just disabled
