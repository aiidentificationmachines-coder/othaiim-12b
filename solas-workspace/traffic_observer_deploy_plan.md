# Complete Production Entity Schema: TrafficObserverLog

Below is the complete production entity schema definition for `TrafficObserverLog` designed to support basic events, AI interaction details, RSI signal calculations, session intelligence, pattern classification, dealer tenant isolation, and session provenance hashes.

## Schema Declaration

**Entity Name:** `TrafficObserverLog`

### Field Definitions

1. **Identity & Context**
   - `userId` (String): Unique identifier of the logged-in user.
   - `userEmail` (String): Email address of the user (primary identifier).
   - `userRole` (String): Role of the user in the system (e.g., "admin", "dealer_rep", "customer").
   - `dealerId` (String): Dealer/Tenant identifier (e.g., "dealer_100").
   - `tenantHash` (String): SHA-256 hash representing the isolated tenant context for safety and performance.
   - `sessionId` (String): Unique session identifier, managed in `sessionStorage` (e.g., `sess_<timestamp>_<random>`).
   - `sessionProvenanceHash` (String): SHA-256 hash of all preceding event payloads within the current session to ensure cryptographic event integrity (provenance).

2. **Event Details**
   - `eventType` (String): Event type badge. Restrained to valid enum values:
     - `PAGE_VIEW`
     - `CLICK`
     - `AI_QUERY`
     - `AI_RATING`
     - `FORM_SUBMIT`
     - `NAVIGATION`
     - `SEARCH`
     - `SESSION_START`
     - `SESSION_END`
   - `eventTimestamp` (Date/Time): ISO-8601 string of the exact event time.
   - `pageName` (String): Human-readable name of the current screen/page (e.g., "AI Quote Studio", "Inventory Manager").
   - `pageUrl` (String): Full absolute URL of the page.
   - `elementId` (String, Optional): ID or descriptor of clicked element (e.g., "btn_generate_quote", "input_customer_phone").
   - `elementType` (String, Optional): Type of element (e.g., "button", "input", "dropdown").
   - `inputValue` (String, Optional): Sanitized and anonymized input value (all PII stripped before ingestion).
   - `deviceType` (String): Client platform (e.g., "desktop", "mobile", "tablet").
   - `ipRegion` (String, Optional): General geographical region (no specific IP stored for privacy compliance).
   - `referrer` (String, Optional): Referring page URL.

3. **AI Interaction Detail**
   - `aiQuery` (String, Optional): Full query typed into the AI assistant by the user.
   - `aiResponse` (String, Optional): AI output text (truncated to first 200 characters for high-density indexing).
   - `aiRating` (Integer, Optional): User star rating (scale 1 to 5) for the AI response.
   - `aiEditDelta` (Integer, Optional): Percentage change (0 to 100) indicating how much the user edited the generated AI output.
   - `aiIntentType` (String, Optional): Classified intention of the AI call (e.g., "build_quote", "check_pipeline", "parts_lookup").
   - `responseMs` (Integer, Optional): AI response generation latency in milliseconds.

4. **RSI Signal Fields**
   - `arScore` (Float, Optional): Actuation Ratio score (system action translation rate).
   - `prScore` (Float, Optional): Promotion Ratio score (user elevation/advancement value).
   - `srScore` (Float, Optional): Session Satisfaction/Rating Score (overall session quality metrics 0 to 1).
   - `rsiSignalType` (String): Classification of signal contribution:
     - `PR_SIGNAL` (Prompt Promotion / AI Rating)
     - `AR_SIGNAL` (Actuation Query impact)
     - `OUTCOME_SIGNAL` (Goal completed, e.g. Form Submit)
     - `ENGAGEMENT_SIGNAL` (Interactive Click)
     - `PASSIVE` (Simple view/read action)
   - `rsiSignalStrength` (Float): Weighted strength of this individual event towards the RSI calculation (0.0 to 1.0).

5. **Session Intelligence**
   - `engagementScore` (Float): Real-time calculated event engagement score (0.0 to 1.0).
   - `frictionScore` (Float): Real-time calculated user friction metric (0.0 to 1.0, derived from speed, retries, and errors).
   - `anomalyScore` (Float): Suspicious or outlier behavior rating (0.0 to 1.0).
   - `userPattern` (String): Classified behavior archetype badge (e.g., "PowerUser", "QuoteResearcher", "PassiveObserver", "Spammer").

---

# Complete Admin Dashboard Layout Design

Designed under **Iconic Workflow's** existing dark theme styling rules:
- **Background:** `#0A0A0A` (Deepest Dark Carbon)
- **Primary/Accent:** `#FF4800` (Electric Safety Orange)
- **Secondary Dark:** `#161616` (Elevated Panel Grey)
- **Borders:** `#262626` (Subtle Wireframe)
- **Typography:** Monochrome Off-White (`#F5F5F5`) with Orange text highlights.

## Wireframe & Layout Blueprint

### TOP BAR (Full Width)
```
+--------------------------------------------------------------------------------------------------------------------------------------+
| [Iconic Orange Logo]  TRAFFIC OBSERVER                                                                                               |
|                       Real-Time Behavior Intelligence · RSI Signal Feed                                                             |
|                                                                                                                                      |
| [Stats Row]                                                                                                                          |
| Total Sessions Today: 142  |  Active Users: 12  |  AI Queries Today: 412  |  Avg Rating: 4.8★  |  RSI Signals Generated: 89          |
|                                                                                                                                      |
| [Filters & Controls]                                                                                                                 |
| Date Range: [ Today / This Week / This Month / Custom ]  |  Search Email: [ enter email... ]                       [ EXPORT CSV ]   |
+--------------------------------------------------------------------------------------------------------------------------------------+
```

### MAIN GRID (Two-Column Layout)

```
+-------------------------------------------------------------+------------------------------------------------------------------------+
| LEFT COLUMN (60% Width)                                     | RIGHT COLUMN (40% Width)                                               |
+-------------------------------------------------------------+------------------------------------------------------------------------+
| Panel 1 — LIVE EVENT FEED (Auto-refresh 15s)                | Panel 3 — USER DEEP DIVE                                               |
| Filter Pills: [ ALL ] [ PAGE_VIEW ] [ AI_QUERY ] [ CLICK ]  | [ Inspect a user: [ Search Email Input ]             ]                 |
|                                                             |                                                                        |
| • 16:15:02  [alice@base44.com] ✦  [AI_QUERY]  AI Quote Studio| • Email: bob@equipmentdealer.com | Archetype: [ QuoteResearcher ] (94%)|
|   "Generated rental agreement for Cat 320" (RSI: 0.4 AR)    | • First Seen: 2026-07-10 09:00  | Last Seen: 2026-07-12 15:42           |
|                                                             | • Total Sessions: 14 | Pages Visited: 8 | AI Queries: 42               |
| • 16:14:50  [dealer_rep@wix.com] ✦ [AI_RATING] AI Studio    | • RSI Contribution: AR: 0.78, PR: 0.85, SR: 0.90                       |
|   "Rated response 5 stars" (RSI: 1.0 PR)                    |                         [ VIEW FULL TIMELINE ]                         |
|                                                             |------------------------------------------------------------------------|
| • 16:14:22  [customer@external.com] [CLICK] Inventory Page  | Panel 4 — RSI SIGNAL MONITOR                                           |
|   "Clicked 'View Specifications' button" (RSI: 0.2 ENGAGE) | This Week's Signal Counts:                                             |
|                                                             | • PR_SIGNAL: 240  | AR_SIGNAL: 180  | OUTCOME: 55  | PASSIVE: 1,420       |
| • 16:13:58  [internal@base44.com] ✦ [PAGE_VIEW] Dashboard   | PR Trend (7d avg rating):     [ Sparkline Rate: 4.2 -> 4.8 ]           |
|   "Visited admin metrics control board"                     | AR Trend (7d edit delta avg):  [ Sparkline Delta: 12% -> 4% ]          |
|                                                             | SR Trend (Session Satisfaction):[ Sparkline SR: 0.75 -> 0.91 ]         |
| ... [Displays last 100 scrollable events]                  |                      [ PUSH TO RSI CALIBRATION ]                       |
|                                                             | Last Calibrated: Today, 12:04 PM                                       |
|-------------------------------------------------------------|------------------------------------------------------------------------|
| Panel 2 — SESSION TIMELINE (Appears on User Select)         | Panel 5 — ANOMALY ALERTS                                               |
| Current Session: sess_17124023948 (User: alice@base44.com)  | • [ CRITICAL ] @base44.com Access Detected (16:15:02)         [Dismiss]|
|                                                             | • [ WARNING ]  PR Starvation warning: No ratings in 7+ days   [Dismiss]|
| O-------O-------O-------O-------O                           | • [ INFO ]     Unusual spike in AI Queries from Tenant #4     [Dismiss]|
| VIEW  CLICK  QUERY  RATING  SUBMIT                          |------------------------------------------------------------------------|
|                                                             | Panel 6 — PAGE HEATMAP                                                 |
| RSI Impact Bar Chart:                                       | 1. AI Quote Studio      ========================= (245 visits) [Orange]|
| [■■ 0.1] [■■■■ 0.2] [■■■■■■■■ 0.4] [■■■■■■■■■■ 1.0]         | 2. Inventory Manager    =====================     (210 visits) [Orange]|
|                                                             | 3. Customer Directory   ==================        (180 visits) [Orange]|
| Hover Tooltip: "AI_RATING Event: Rated 5-stars. Impact PR"  | 4. Work Order Dispatch  ===========               (110 visits) [Grey]  |
|                                                             | 5. Points Leaderboard   =======                   (70 visits)  [Grey]  |
+-------------------------------------------------------------+------------------------------------------------------------------------+

### BOTTOM FULL WIDTH PANEL
+--------------------------------------------------------------------------------------------------------------------------------------+
| Panel 7 — DEALER COMPARISON (Admin Only)                                                                                              |
| Tenant ID        | Total Active Users | AI Ratings Submitted | Avg Edit Delta % | PR Signals | AR Signals | RSI Calibration Progress  |
|------------------|--------------------|----------------------|------------------|------------|------------|---------------------------|
| tenant_hbs_01    | 42                 | 152                  | 4.2%             | 145        | 98         | [████████████░░░] 82%     |
| tenant_local_09  | 18                 | 48                   | 18.5%            | 38         | 22         | [██████░░░░░░░░░] 40%     |
| tenant_paycor_11 | 29                 | 88                   | 7.1%             | 74         | 50         | [██████████░░░░░] 64%     |
+--------------------------------------------------------------------------------------------------------------------------------------+
```

---

# Recommended Deployment Steps

To register the entity schema, build the frontend hook, and activate the administrative user interface, execute the following actions:

1. **Entity Provisioning:** Create the `TrafficObserverLog` entity utilizing the schema fields detailed above.
2. **Backend Engine Route Verification:** Ensure that `functions/trafficObserverEngine.ts` is fully compatible with the fields written here (already confirmed as compatible).
3. **Frontend Integration:** Place the frontend tracking hook in the main root application routing framework.
4. **Admin Panel Construction:** Build the `Traffic Observer` admin screen component under the Iconic Workflow application.
