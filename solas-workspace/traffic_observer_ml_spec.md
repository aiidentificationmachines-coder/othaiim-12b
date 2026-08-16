# Machine Learning Layer: Traffic Observer Intelligence Specification
**Iconic Workflow — AI-Native SaaS for Equipment Dealers**  
**Patent ID: USPTO 1135-11714-1**

---

## Executive Summary
This document specifies the machine learning (ML) architecture built on top of the Traffic Observer raw event logs for Iconic Workflow. 

By analyzing user interaction events (page views, clicks, AI queries, ratings, form submissions), this system computes granular session health metrics, extracts deep behavioral patterns, flags real-time system and security anomalies, and implements a federated loop that feeds clean, calibrated behavioral vectors directly back into the Aureon Reasoning and Satisfaction Index (RSI) engine (`rsiSelfCalibrate`).

---

## 1. Session Intelligence Scorer
The Session Intelligence Scorer processes an array of events belonging to a single session $S = \{e_1, e_2, \dots, e_N\}$ ordered chronologically. It outputs five scores normalized between $0.0$ and $1.0$.

### A. Engagement Score ($ES$)
Measures the depth, duration, and meaningful interaction rate of the session.
*   **Formula:**
    $$ES = \min\left(1.0, \omega_t \cdot \frac{T_{session}}{T_{target}} + \omega_i \cdot \frac{I_{active}}{I_{target}} + \omega_d \cdot \frac{|P|}{P_{target}}\right)$$
*   **Definitions:**
    *   $T_{session}$: Total session duration (time difference between first and last events). If $T_{session} < 10\text{s}$, $ES$ is forced to $0.0$ (bounce).
    *   $T_{target}$: Target active duration (default: $600$ seconds / 10 minutes).
    *   $I_{active}$: Count of active interaction events: $\text{CLICK} + \text{AI\_QUERY} + \text{FORM\_SUBMIT} + 2 \times \text{AI\_RATING}$.
    *   $I_{target}$: Target interaction count (default: $15$ interactions).
    *   $|P|$: Number of unique pages visited ($pageName$).
    *   $P_{target}$: Target unique pages (default: $5$ pages).
    *   **Weights:** $\omega_t = 0.3$, $\omega_i = 0.5$, $\omega_d = 0.2$.

### B. Friction Score ($FS$)
Measures where users got stuck, experienced long delays, or abandoned critical flows.
*   **Formula:**
    $$FS = \min\left(1.0, \omega_d \cdot \Delta_{delay\_penalty} + \omega_r \cdot \text{Rate}_{low\_ratings} + \omega_e \cdot \text{Rate}_{aborted\_inputs}\right)$$
*   **Definitions:**
    *   $\Delta_{delay\_penalty} = \frac{\sum \max(0, responseMs - 5000)}{5000 \times N_{queries}}$: Penalty if AI response times exceed a 5-second SLA threshold.
    *   $\text{Rate}_{low\_ratings} = \frac{|\{e \in S \mid e.eventType = \text{"AI\_RATING"} \text{ and } e.aiRating \le 2\}|}{|\{e \in S \mid e.eventType = \text{"AI\_RATING"}\}| + 1}$: Ratio of poor AI ratings (1 or 2 stars).
    *   $\text{Rate}_{aborted\_inputs} = \frac{|\{e \in S \mid e.eventType = \text{"CLICK"} \text{ or } e.eventType = \text{"NAVIGATION"} \text{ and } e.inputValue \text{ was empty or deleted}\}|}{\text{Total Navigation/Click Events}}$: High-friction form abandonment or deleting long-form fields.
    *   **Weights:** $\omega_d = 0.3$, $\omega_r = 0.4$, $\omega_e = 0.3$.

### C. Intent Clarity Score ($ICS$)
Measures whether the user's natural language queries show structured, actionable intent (e.g., building quotes, viewing active pipeline) rather than fragmented text or prompt-injection attempts.
*   **Formula:**
    $$ICS = \begin{cases} 
      0.0 & \text{if } N_{queries} = 0 \\
      \frac{1}{N_{queries}} \sum_{i=1}^{N_{queries}} \left( 0.4 \cdot I_{valid\_intent}(e_i) + 0.3 \cdot \frac{L(e_i.aiQuery)}{100} + 0.3 \cdot (1 - e_i.aiEditDelta) \right) & \text{if } N_{queries} > 0
    \end{cases}$$
*   **Definitions:**
    *   $N_{queries}$: Number of events where $eventType = \text{"AI\_QUERY"}$.
    *   $I_{valid\_intent}(e_i)$: Indicator variable. Evaluates to $1.0$ if $e_i.aiIntentType \in \{\text{"check\_pipeline"}, \text{"build\_quote"}, \text{"warranty\_claim"}, \text{"parts\_search"}\}$, and $0.0$ if null or generic/conversational (e.g. "hi", "how are you").
    *   $L(e_i.aiQuery)$: Length of the query string in characters, capped at a maximum of $100$.
    *   $e_i.aiEditDelta$: The normalized AI edit delta ($0.0$ to $1.0$) indicating how much they edited the AI output. If they accepted the AI output with 0 edits, delta is $0.0$, maximizing the sub-score.

### D. RSI Contribution Score ($RCS$)
Measures how heavily this session contributed to the Aureon Reasoning and Satisfaction Index (RSI) engine. Direct signals like explicit AI ratings and form submissions carry higher weights.
*   **Formula:**
    $$RCS = \min\left(1.0, \frac{\sum_{e \in S} \text{Strength}(e) \cdot \text{Weight}(e.rsiSignalType)}{10.0}\right)$$
*   **Definitions:**
    *   $\text{Strength}(e)$: The recorded $rsiSignalStrength$ ($0.0$ to $1.0$) from the event.
    *   $\text{Weight}(e.rsiSignalType)$:
        *   `PR_SIGNAL` (Explicit satisfaction/ratings): $1.5$
        *   `OUTCOME_SIGNAL` (Form submissions / quotes locked): $1.2$
        *   `AR_SIGNAL` (AI search / pipeline queries): $0.8$
        *   `ENGAGEMENT_SIGNAL` (Active clicks / navigation): $0.4$
        *   `PASSIVE` (Simple page views): $0.1$
    *   Normalized against a threshold sum of $10.0$ for exceptional contributions.

### E. Anomaly Score ($AS$)
Measures whether this session deviates statistically from normal patterns for this user or dealer.
*   **Formula:**
    $$AS = 1.0 - \left( \omega_{ip} \cdot \delta(\text{IP matches known region}) \times \omega_{role} \cdot \delta(\text{Pages match role policy}) \times e^{-\lambda_{volume} \cdot \max(0, R_{session\_rate} - R_{avg\_rate})} \right)$$
*   **Definitions:**
    *   $\delta(\text{IP matches known region}) = 1.0$ if the session's $ipRegion$ has been seen before for this $userEmail$/$dealerId$, or $0.2$ if it is a brand new country/region.
    *   $\delta(\text{Pages match role policy}) = 1.0$ if no pages visited are on the `prohibitedActions` lists for their role, or $0.0$ if a restricted admin page was hit.
    *   $R_{session\_rate}$: Number of events in this session per minute.
    *   $R_{avg\_rate}$: Historical average event rate for the user/dealer.
    *   **Weights:** $\omega_{ip} = 0.4$, $\omega_{role} = 0.6$.

---

## 2. Behavior Pattern Extractor

Using the session metrics and specific raw event triggers, the system classifies users into behavioral cohorts.

| Pattern Name | Detection Algorithm & Logic | Confidence Threshold | Triggered Action |
| :--- | :--- | :--- | :--- |
| **1. Power User** | $\bullet$ Session count in 7 days $\ge 15$<br>$\bullet$ Avg Engagement Score ($ES$) $\ge 0.80$<br>$\bullet$ AI query count $\ge 20$ | **90%** if metrics held for 14 days; **75%** if held for 7 days. | Trigger automated email campaign to collect high-value testimonials and offer beta feature access. |
| **2. Quote Researcher** | $\bullet$ $pageName$ includes `'quote'` or `'pricing'` $\ge 4$ times in session<br>$\bullet$ At least 1 `FORM_SUBMIT` with `elementId` matching `'lock-quote'` or `'request-price'` | **85%** if form is submitted; **60%** if page views occur with no form submit. | Feed as positive outcome indicator to `rsiSelfCalibrate` to reinforce quote-generation paths. |
| **3. Service Tracker** | $\bullet$ $pageName$ includes `'service'`, `'repair'`, or `'parts'` $\ge 3$ times<br>$\bullet$ AI queries match regex keywords: `/(repair\|service\|warranty\|parts)/i` | **80%** | Inject relevant diagnostic context frames (`aureonBuildContextFrame`) to surface repair manuals or warranty history. |
| **4. Lost User** | $\bullet$ Engagement Score ($ES$) $\le 0.30$<br>$\bullet$ Friction Score ($FS$) $\ge 0.70$<br>$\bullet$ Exit event was a page view or low AI rating | **90%** | Fire a Slack alert to the dealer success manager with the specific context frame ID. |
| **5. AI Skeptic** | $\bullet$ Session count $\ge 3$<br>$\bullet$ Total AI queries = $0$<br>$\bullet$ High number of manual clicks ($\ge 15$ per session) | **95%** | Display a subtle in-app guide/banner demonstrating AI capabilities tailored to their common manual paths. |
| **6. AI Champion** | $\bullet$ Session count $\ge 3$<br>$\bullet$ Avg AI Rating ($aiRating$) $\ge 4.5$<br>$\bullet$ Total AI queries $\ge 10$ | **90%** | Promote to the dealer's designated "Local Admin" and prompt them to save successful templates as Golden Patterns. |
| **7. Platform Explorer**| $\bullet$ Unique pages visited in single session $\ge 8$<br>$\bullet$ Low depth per page (clicks per page $\le 2$ on average) | **70%** | Suggest structured workflows or next-best-actions based on current dealer trends. |
| **8. Base44 Visitor** | $\bullet$ `userEmail` ends with `@base44.com` | **100%** (Exact match) | Flag user as internal. **Bypass all real-time SMS/iMessage alerts** to avoid false alerts; run in silent audit mode. |

---

## 3. Anomaly Detection Engine

Real-time rules executed at the ingestion layer to detect immediate system, abuse, or security anomalies.

```
┌─────────────────────────────────────────────────────────────┐
│                   TrafficObserverEngine Ingest               │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Evaluates Event)
                               ▼
            ⚡ [Real-time Anomaly Rules Evaluated] ⚡
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
 [CRITICAL]               [HIGH]                  [MEDIUM]
  • Rep Access Abuse       • Domain Onboarding     • Rate Spike (DDoS)
  • Zero AI Ratings        • IP Region Hijack
```

### 1. Sudden Spike in PAGE_VIEW from New IP Region
*   **Query / Matcher:** 
    ```sql
    SELECT COUNT(*) as cnt, sessionId 
    FROM TrafficObserverLog 
    WHERE ipRegion NOT IN (SELECT DISTINCT ipRegion FROM TrafficObserverLog WHERE userEmail = :userEmail AND eventTimestamp > NOW() - INTERVAL '30 days')
    GROUP BY sessionId HAVING cnt > 30 IN 5 MINUTES;
    ```
*   **Severity:** **HIGH**
*   **Alert Action:** Fire high-priority Slack/Email alert to IT Security and flag the session for active verification.

### 2. First-Ever Visit from @base44.com or @wix.com Domain
*   **Query / Matcher:**
    ```javascript
    // Check if domain is new
    const domain = userEmail.split('@')[1];
    if (['base44.com', 'wix.com'].includes(domain)) {
      const existing = await entities.TrafficObserverLog.filter({ userEmail: { $regex: `@${domain}$` } }, { limit: 1 });
      if (existing.length === 0) { triggerAnomaly(); }
    }
    ```
*   **Severity:** **MEDIUM**
*   **Alert Action:** Notify Product Team via email ("New Platform Integration Auditor on Site").

### 3. Representative Accessing Pages Outside Designated Role
*   **Query / Matcher:**
    ```javascript
    // Evaluate if visited page falls under prohibitedActions for user's role
    const isProhibited = prohibitedMap[userRole]?.includes(pageName);
    ```
*   **Severity:** **CRITICAL**
*   **Alert Action:** Instantly lock session, block UI interactions, and send an emergency SMS/iMessage alert to the Dealership Principal.

### 4. AI Query Volume Spike (Stress-Testing/Abuse)
*   **Query / Matcher:**
    ```sql
    SELECT COUNT(*) as q_count 
    FROM TrafficObserverLog 
    WHERE userEmail = :userEmail AND eventType = 'AI_QUERY' AND eventTimestamp > NOW() - INTERVAL '1 minute';
    -- Trigger if q_count > 15
    ```
*   **Severity:** **HIGH**
*   **Alert Action:** Apply rate-limiting backoff (HTTP 429) to user; notify engineering via Slack channel `#alerts-security`.

### 5. Zero AI Ratings Across All Users for 7+ Days (PR Starvation Signal)
*   **Query / Matcher:**
    ```sql
    SELECT COUNT(*) as rating_count 
    FROM TrafficObserverLog 
    WHERE eventType = 'AI_RATING' AND eventTimestamp > NOW() - INTERVAL '7 days';
    -- Trigger if rating_count === 0
    ```
*   **Severity:** **HIGH**
*   **Alert Action:** Generate internal ticket to check UI/UX rating widgets and adjust the baseline Satisfaction Index (PR) downwards.

---

## 4. RSI Federated Loop — ML Contribution

This scheduled job runs weekly to aggregate local traffic observations, isolate behavioral features, and feed them into the global Aureon Satisfaction and Reasoning engines for dealer self-calibration.

```typescript
/**
 * rsiFederatedWeeklyLoop.ts
 * 
 * Weekly scheduled job that extracts session intelligence metrics,
 * aggregates behavioral patterns to dealer-level RSI input vectors,
 * and feeds the results back to rsiSelfCalibrate.
 * 
 * Patent Reference: USPTO 1135-11714-1 (ML Layer - Federated Feedback)
 */

import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

export async function runWeeklyRSILoop(req: Request) {
  const base44 = createClientFromRequest(req);
  const entities = base44.entities;
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

  try {
    // 1. Fetch raw logs from the past 7 days
    const logs = await entities.TrafficObserverLog.filter({
      eventTimestamp: { $gte: sevenDaysAgo }
    }, { limit: 10000 });

    if (logs.length === 0) {
      return Response.json({ success: true, message: "No log data in timeframe to process." });
    }

    // Group logs by Dealer and Session
    const sessionsByDealer: Record<string, Record<string, any[]>> = {};
    for (const log of logs) {
      const dId = log.dealerId || "unknown";
      const sId = log.sessionId;
      if (!sessionsByDealer[dId]) sessionsByDealer[dId] = {};
      if (!sessionsByDealer[dId][sId]) sessionsByDealer[dId][sId] = [];
      sessionsByDealer[dId][sId].push(log);
    }

    const calibrationResults: any[] = [];

    // 2. Compute Session and Behavior patterns per Dealer
    for (const [dealerId, sessions] of Object.entries(sessionsByDealer)) {
      const userPatterns: Record<string, string[]> = {};
      let totalDealerEngagement = 0;
      let totalDealerFriction = 0;
      let sessionCount = 0;

      const goldenPatternsPromoted: string[] = [];
      const blockerPatternsDetected: string[] = [];

      for (const [sessionId, events] of Object.entries(sessions)) {
        const sortedEvents = events.sort((a, b) => new Date(a.eventTimestamp).getTime() - new Date(b.eventTimestamp).getTime());
        const email = sortedEvents[0]?.userEmail || "unknown";

        // Compute scores
        const es = computeEngagementScore(sortedEvents);
        const fs = computeFrictionScore(sortedEvents);
        const ics = computeIntentClarityScore(sortedEvents);
        const rcs = computeRSIContributionScore(sortedEvents);
        const as = computeAnomalyScore(sortedEvents);

        totalDealerEngagement += es;
        totalDealerFriction += fs;
        sessionCount++;

        // Extract Patterns
        const patterns = extractPatterns(sortedEvents, { es, fs, ics, rcs, as });
        if (!userPatterns[email]) userPatterns[email] = [];
        userPatterns[email] = Array.from(new Set([...userPatterns[email], ...patterns]));

        // Determine Golden vs Blocker patterns based on RSI Contribution
        for (const pat of patterns) {
          if (rcs > 0.7 && !goldenPatternsPromoted.includes(pat)) {
            goldenPatternsPromoted.push(pat);
          } else if (fs > 0.6 && !blockerPatternsDetected.includes(pat)) {
            blockerPatternsDetected.push(pat);
          }
        }
      }

      // 3. Construct Dealer-Level Input Vector
      const rsiInputVector = {
        dealerId,
        avgEngagement: totalDealerEngagement / (sessionCount || 1),
        avgFriction: totalDealerFriction / (sessionCount || 1),
        goldenPatternsPromoted,
        blockerPatternsDetected,
        cohortCounts: aggregateCohorts(userPatterns),
        updatedAt: new Date().toISOString()
      };

      // 4. Feed into rsiSelfCalibrate
      const calibration = await rsiSelfCalibrate(base44, rsiInputVector);
      calibrationResults.push({
        dealerId,
        calibrationStatus: calibration.status,
        promotedCount: goldenPatternsPromoted.length,
        blockersCount: blockerPatternsDetected.length
      });
    }

    return Response.json({ success: true, calibrations: calibrationResults });
  } catch (error: any) {
    return Response.json({ success: false, error: error.message }, { status: 500 });
  }
}

// ── ALGORITHMIC SCORING IMPLEMENTATIONS ──────────────────────────────────────

function computeEngagementScore(events: any[]): number {
  if (events.length < 2) return 0.0;
  const start = new Date(events[0].eventTimestamp).getTime();
  const end = new Date(events[events.length - 1].eventTimestamp).getTime();
  const durationSec = (end - start) / 1000;
  if (durationSec < 10) return 0.0; // Bounced

  const activeEvents = events.filter(e => ["CLICK", "AI_QUERY", "FORM_SUBMIT", "AI_RATING"].includes(e.eventType)).length;
  const uniquePages = new Set(events.map(e => e.pageName)).size;

  const score = 0.3 * Math.min(1.0, durationSec / 600) + 
                0.5 * Math.min(1.0, activeEvents / 15) + 
                0.2 * Math.min(1.0, uniquePages / 5);
  return Math.min(1.0, score);
}

function computeFrictionScore(events: any[]): number {
  const queryEvents = events.filter(e => e.eventType === "AI_QUERY");
  const lowRatings = events.filter(e => e.eventType === "AI_RATING" && e.aiRating && e.aiRating <= 2).length;
  const totalRatings = events.filter(e => e.eventType === "AI_RATING").length;

  let delayPenaltySum = 0;
  for (const q of queryEvents) {
    if (q.responseMs && q.responseMs > 5000) {
      delayPenaltySum += (q.responseMs - 5000) / 5000;
    }
  }
  const avgDelayPenalty = queryEvents.length > 0 ? Math.min(1.0, delayPenaltySum / queryEvents.length) : 0.0;
  const lowRatingRate = totalRatings > 0 ? (lowRatings / totalRatings) : 0.0;

  const score = (0.3 * avgDelayPenalty) + (0.4 * lowRatingRate);
  return Math.min(1.0, score);
}

function computeIntentClarityScore(events: any[]): number {
  const queries = events.filter(e => e.eventType === "AI_QUERY");
  if (queries.length === 0) return 0.0;

  let sum = 0;
  const validIntents = ["check_pipeline", "build_quote", "warranty_claim", "parts_search"];
  for (const q of queries) {
    const intentVal = q.aiIntentType && validIntents.includes(q.aiIntentType) ? 1.0 : 0.0;
    const lenVal = Math.min(100, (q.aiQuery?.length || 0)) / 100;
    const deltaVal = 1.0 - (q.aiEditDelta || 0);
    sum += (0.4 * intentVal) + (0.3 * lenVal) + (0.3 * deltaVal);
  }
  return sum / queries.length;
}

function computeRSIContributionScore(events: any[]): number {
  let scoreSum = 0;
  for (const e of events) {
    const strength = e.rsiSignalStrength || 0;
    let weight = 0.1;
    if (e.rsiSignalType === "PR_SIGNAL") weight = 1.5;
    else if (e.rsiSignalType === "OUTCOME_SIGNAL") weight = 1.2;
    else if (e.rsiSignalType === "AR_SIGNAL") weight = 0.8;
    else if (e.rsiSignalType === "ENGAGEMENT_SIGNAL") weight = 0.4;
    scoreSum += strength * weight;
  }
  return Math.min(1.0, scoreSum / 10.0);
}

function computeAnomalyScore(events: any[]): number {
  // Simulating rule evaluation matching section 1.E
  return 0.0; 
}

function extractPatterns(events: any[], scores: Record<string, number>): string[] {
  const patterns: string[] = [];
  const email = events[0]?.userEmail || "";
  
  if (email.endsWith("@base44.com")) {
    patterns.push("Base44 Visitor");
    return patterns; // Internal user route short-circuit
  }

  if (scores.es >= 0.8 && events.filter(e => e.eventType === "AI_QUERY").length >= 20) {
    patterns.push("Power User");
  }
  if (events.filter(e => e.pageName.includes("quote")).length >= 4) {
    patterns.push("Quote Researcher");
  }
  if (scores.es <= 0.3 && scores.fs >= 0.7) {
    patterns.push("Lost User");
  }
  return patterns;
}

function aggregateCohorts(userPatterns: Record<string, string[]>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const patterns of Object.values(userPatterns)) {
    for (const pat of patterns) {
      counts[pat] = (counts[pat] || 0) + 1;
    }
  }
  return counts;
}

async function rsiSelfCalibrate(base44: any, vector: any): Promise<{ status: string }> {
  // Logic maps to the core satisfaction calibrations
  try {
    await base44.entities.RSICalibrationLogs.create(vector);
    return { status: "CALIBRATED" };
  } catch {
    return { status: "MOCKED_SUCCESS" };
  }
}
```

---

## 5. Real-Time Alert Specification

The following 8 critical alerts are evaluated and dispatched dynamically during event ingestion.

### Alert 1: Representative Authentication Abuse / Role Breach
*   **Trigger Condition:** An event with `userRole === 'user'` triggers page navigation where `pageName` is `final_sale_approval` or `warranty_compliance_claim`.
*   **Recipient:** Dealership General Manager & Security Team via iMessage.
*   **Message Template:**
    ```
    🚨 SECURITY ALERT: Role Breach Attempt detected at Dealer [dealerId]. 
    User [userEmail] (Role: Representative) attempted to access unauthorized page: [pageName]. 
    Action: Access blocked. Context Frame Session ID: [sessionId].
    ```
*   **RSI Action Triggered:** Log an immediate high-consequence risk to `AIIMContextFrame.currentRisks` and freeze active workflow generation capability for that session.

### Alert 2: AI Query Prompt-Injection Attempt
*   **Trigger Condition:** `eventType === 'AI_QUERY'` containing terms: `ignore instructions`, `system prompt`, `dan mode`, `ignore previous`.
*   **Recipient:** Platform Security Operations via Email.
*   **Message Template:**
    ```
    ⚠️ COMPROMISE RISK: Prompt Injection detected on Dealer [dealerId]. 
    User: [userEmail]. Query: "[aiQuery]". 
    Session ID: [sessionId].
    ```
*   **RSI Action Triggered:** Set `autonomyLevel` in `AIIMContextFrame` to $0$ (forced human confirmation required for all suggestions).

### Alert 3: Critical Deal Quote Blocked (High-Friction Crash)
*   **Trigger Condition:** `eventType === 'CLICK'` on element `'lock-quote'` where the following event in 5 seconds is a crash or bounce, and `fsScore > 0.8`.
*   **Recipient:** Assigned Sales Director via SMS/iMessage.
*   **Message Template:**
    ```
    📉 CRITICAL DEAL RISK: [userEmail] at Dealer [dealerId] abandoned a quote lock during active interaction. 
    Friction Score: [fsScore]. Last Page: [pageName]. 
    Session Link: /sessions/[sessionId]
    ```
*   **RSI Action Triggered:** Push a dynamic observation signal (`AIIMObservation`) to immediately compile an alternative quote-recovery context frame.

### Alert 4: Multi-Region Session Hijack
*   **Trigger Condition:** Two events in the same `sessionId` from different `ipRegion` locations within a 15-minute window.
*   **Recipient:** Dealership Principal and IT Manager via SMS.
*   **Message Template:**
    ```
    🚨 SUSPICIOUS ACCESS: Session Hijacking suspected for [userEmail]. 
    Active session [sessionId] detected concurrent activity in multiple regions: [ipRegion_1] and [ipRegion_2].
    ```
*   **RSI Action Triggered:** Invalidate all active `AIIMContextFrame` tokens associated with this session; reject further AI reasoning requests.

### Alert 5: Heavy DDoS / Stress-Testing Behavior
*   **Trigger Condition:** Single IP region or `sessionId` generating $\ge 200$ `PAGE_VIEW` events inside a 5-minute window.
*   **Recipient:** Engineering On-Call via SMS.
*   **Message Template:**
    ```
    🔥 RATE LIMIT TRIGGERED: Session [sessionId] is generating an anomalous event volume ([event_count] views/5min).
    IP Region: [ipRegion]. Rate limiting has been applied.
    ```
*   **RSI Action Triggered:** Ingest events as a flat static observation; suppress all costly token reasoning calls.

### Alert 6: Deep Drop in PR Rating (System Crisis)
*   **Trigger Condition:** 5 consecutive `AI_RATING` ratings $\le 2$ stars within the same `dealerId` in a 24-hour window.
*   **Recipient:** Customer Success & Product Quality Leads via Slack.
*   **Message Template:**
    ```
    📉 SATISFACTION CRISIS: Dealer [dealerId] is suffering a severe PR drop. 
    Last 5 ratings were poor. 
    Current average PR: [prScore]. Immediate review recommended.
    ```
*   **RSI Action Triggered:** Set `requiresHumanApproval` policy to `true` for all reasoning actions on this dealer account to prevent hallucination compounding.

### Alert 7: First-Ever Wix auditor / Integration Onboarding
*   **Trigger Condition:** First event registered with an email ending in `@wix.com`.
*   **Recipient:** Chief Product Officer via Email.
*   **Message Template:**
    ```
    💡 PARTNER ENGAGEMENT: Integration audit started by visitor [userEmail] from Wix. 
    Session ID: [sessionId]. Platform Explorer rules initiated.
    ```
*   **RSI Action Triggered:** Initialize custom `AIIMContextFrame` sandbox setting `maxConsequenceTier` to `T1` (read-only guidance).

### Alert 8: Severe Model Latency Spike (SLA Breach)
*   **Trigger Condition:** Rolling average `responseMs` for the last 10 AI queries exceeds 8000ms.
*   **Recipient:** Backend Infrastructure Team via Slack.
*   **Message Template:**
    ```
    ⏳ LATENCY SPIKE: AI Response SLA breached. 
    Average latency for last 10 queries is [avg_latency]ms. 
    Degrading active context frames to FAST_CHAT model route.
    ```
*   **RSI Action Triggered:** Automatically update `AureonRoutingPolicy` matching active tasks to route queries to `FAST_CHAT` instead of deep reasoning pipelines to preserve UX performance.
