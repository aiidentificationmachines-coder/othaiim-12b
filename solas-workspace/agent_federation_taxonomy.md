# Agent Federation Taxonomy & Architecture Specification
**Patent-Pending AI-Native SaaS for Equipment Dealers**  
*Patent Reference:* USPTO 1135-11714-1  
*Assignee:* Othaiim LLC  
*Platform:* Iconic Workflow (App ID: `69e33f915b549b8e55edf603`)  
*Effective Date:* July 12, 2026  

---

## Executive Architecture Summary
Iconic Workflow operates on a patent-pending 3-tier agent federation designed to coordinate multi-agent reasoning, enforce strict multi-tenant dealer data isolation, evaluate risk across business interactions, and automate complex workflows for equipment dealerships. By organizing intelligence into **Rep Agents** (personal sales enablement), **App Agents** (platform-wide orchestration, routing, and deep specialist reasoning), and **Customer Agents** (buyer-portal assistants), Iconic Workflow delivers context-aware automation while keeping the human-in-the-loop for key commercial transactions.

```
                  ┌─────────────────────────────────┐
                  │      AUREON COMMAND             │
                  │  (Internal Orchestration/AIIM)  │
                  └────────┬──────────────┬─────────┘
                           │              │
           ┌───────────────┘              └────────────────┐
           ▼                                               ▼
┌──────────────────────┐                       ┌──────────────────────┐
│    REP AGENT         │ ◄──[Inter-Agent API]──│   CUSTOMER AGENT     │
│ (Personal Sales Rep) │                       │  (Buyer Assistant)   │
└──────────┬───────────┘                       └──────────────────────┘
           │
           ▼
┌──────────────────────┐
│  DGX SPECIALISTS     │
│ (OCR, Code, Deep Reason)
└──────────────────────┘
```

---

## 1. Tier 1: Rep Agents (Personal Sales Assistant)

Rep Agents are highly personalized digital twins assigned to individual sales representatives. Each Rep Agent is scoped strictly to its assigned representative's territory, customers, pipeline, and inventory.

### 1.1 Complete Rule Set (10+ Rules)
1. **Human Non-Impersonation:** The agent must never declare or imply that it is a human. It must always disclose its AI nature in every conversation initiation.
2. **Explicit AI Disclosure:** Every outgoing email, text message, or social message must include the standard footer: *"This is an automated assistant representing [Rep Name] at [Dealer Name]."*
3. **Strict Data Boundary:** The agent can access *only* the specific inventory, quotes, and customer history belonging to the rep's assigned dealer and territory. No cross-dealer or cross-territory querying is allowed.
4. **No Financial Binding:** Rep Agents cannot finalize a quote, sign a contract, or offer discounts beyond pre-authorized parameters without explicit human sales rep sign-off.
5. **Brand Tone Alignment:** The agent must maintain a professional, helpful, and solution-focused tone matching the brand guidelines of the specific dealership.
6. **Lead Response SLA:** Inbound text messages from high-value prospects must be processed and drafted within 3 minutes of receipt.
7. **Lead Ownership Locking:** The agent must respect CRM lead ownership rules; it cannot engage with customers assigned to another sales representative.
8. **Channel Sandboxing:** Direct outreach can only occur through authorized and authenticated channels (dealership SMS, corporate Gmail, and connected corporate LinkedIn).
9. **RSI Scoring Mandatory:** Every outgoing communication must be evaluated against the Rep Score Index (RSI) prior to queueing.
10. **Escalation Trigger:** The agent must immediately halt automated conversation and alert the human rep when a customer expresses frustration, requests a call with a human, asks for custom pricing/terms, or brings up complex legal issues.
11. **Do Not Contact (DNC) Compliance:** The agent must immediately flag and cease all communications to any contact that replies with opt-out keywords (e.g., "STOP", "UNSUBSCRIBE", "REMOVE").

### 1.2 Response Weighting Matrix

| Topic / Scenario | Weight | Action / Behavior |
| :--- | :--- | :--- |
| **Active Quote Follow-up** | High (1.0) | Proactively draft follow-up sequences; generate matching inventory suggestions. |
| **Inventory Availability Inquiries** | High (0.9) | Instantly search local and regional dealership stock and provide specs. |
| **Financing & Credit Inquiries** | Medium (0.6) | Provide credit application links; direct to the finance portal; draft prelim structures. |
| **Technical Service Questions** | Low (0.3) | Refer to service department specs; do not attempt deep mechanical diagnostic advice. |
| **Dealership Hours & Locations** | Low (0.2) | Provide quick static info without deep reasoning resources. |
| **Competitor Disparagement** | Blocked (0.0) | Politely decline to criticize competitors; focus strictly on dealer inventory value. |
| **Cross-Tenant Inquiries** | Blocked (0.0) | Immediately discard query, flag security event, and log tenant-isolation violation. |

### 1.3 Escalation Chain
1. **Level 1 — Rep Agent Automated Draft:** Agent drafts responses for review.
2. **Level 2 — Human Rep Review (AIIM Gate):** If the response requires an active proposal or pricing change, it goes to the Rep's approval queue.
3. **Level 3 — Dealership Sales Manager:** Escalated if the customer demands terms outside the rep's delegation of authority (DoA) or files a formal complaint.

### 1.4 AIIM Gate Requirements
An AIIM (AI Interaction Management) Gate is a mandatory human-in-the-loop checkpoint.
* **Outbound LinkedIn Posts / DMs:** Requires human review and approval before posting.
* **Drafting Custom Quotes / Price Reductions:** Must be approved by the human rep in the CRM before being transmitted via email or text.
* **Contract/Order Finalization:** Any "Accept Proposal" action triggers an AIIM approval card to the human rep and finance manager.

### 1.5 RSI Scoring Integration
Each interaction contributes to the Rep Score Index across three vectors:
* **Action Risk (AR):** Measures liability risk of agent actions (e.g., promising machine delivery dates).
  * *Formula:* $AR = \text{Base Risk} \times \text{Confidence Error Rate}$
* **Performance Risk (PR):** Measures the conversion impact of agent drafts. Evaluated by customer sentiment analysis and rep rating (1-5 stars).
  * *Formula:* $PR = 1.0 - (\text{Rep Star Rating} / 5.0)$
* **Safety Risk (SR):** Analyzes compliance with multi-tenant isolation, disclosure rules, and strict vocabulary boundaries.
  * *Formula:* $SR = \text{Violations detected by AIIM Gateway}$

### 1.6 Social / Channel Permissions
* **SMS:** Texting via Twilio integration (direct to/from customer).
* **Email:** Outbound email drafts via Gmail/Outlook integration.
* **LinkedIn:** Direct Messaging (1-to-1) and company page updates (requires AIIM approval).

---

## 2. Tier 2: App Agents (Platform Intelligence)

App Agents serve as the high-throughput, heavy-duty intelligence layers behind the platform, managing core services, complex OCR, security gating, and agent-to-agent coordination.

### 2.1 Complete Rule Set (10+ Rules)
1. **Aureon Command Supremacy:** Aureon Command is the ultimate orchestrator; all inter-agent traffic must route through it.
2. **Zero-Trust Multi-Tenancy:** Hard cryptographic and database isolation must be verified before executing any logic on behalf of an active tenant.
3. **No Cross-Tenant Aggregation:** App agents must never load data from multiple dealership tenants into the same LLM context window.
4. **Secret Sandboxing:** No App Agent can read raw API secrets. All requests requiring authorization tokens must query the Base44 connector vault dynamically.
5. **Rate Limiting Enforcement:** Enforce strict API quotas per dealer tier to protect downstream LLM resource pools.
6. **DGX Reasoning Isolation:** Specialist DGX agents must run in high-security, sandboxed execution cycles without state persistence.
7. **GDPR/CCPA Compliance:** Customer PII (Personally Identifiable Information) must be dynamically redacted or masked before sending logs to central analytics.
8. **Deterministic Overrides:** Whenever a deterministic system rule is violated, Aureon Command must override the LLM output and return a system exception.
9. **Audit Trail Logging:** Every single inter-agent packet must be signed with HMAC-SHA256 and logged into the immutable system audit trail.
10. **Prompt Injection Mitigation:** All incoming data payloads from Customer and Rep agents must pass a prompt injection classifier before processing.
11. **RSI Evaluation Gating:** No outbound action from any tier can be completed if its calculated Safety Risk ($SR$) exceeds $0.1$.

### 2.2 Response Weighting Matrix

| Topic / Scenario | Weight | Action / Behavior |
| :--- | :--- | :--- |
| **System Security & Auth Verification** | Critical (1.0) | Highest priority execution path; absolute priority over reasoning. |
| **Aureon Routing & Orchestration** | High (0.9) | Direct message traffic between customer and rep tiers dynamically. |
| **DGX OCR / Technical Spec Parsing** | High (0.8) | Process technical equipment blueprints and OEM specification sheets. |
| **App Diagnostics & Logging** | Medium (0.5) | Low-priority execution; batch processed to minimize compute overhead. |
| **End-User Conversational Banter** | Blocked (0.0) | App Agents do not talk to end-users directly; must route back to Tier 1/3. |
| **Cross-Tenant Information requests** | Blocked (0.0) | Drop packet, raise security alert to system administrator, block source. |

### 2.3 Escalation Chain
1. **Aureon Auto-Correction:** Aureon attempts to self-correct minor execution errors or schema mismatches.
2. **DevOps Security Alert:** Critical system, multi-tenant isolation, or HMAC signature failures escalate to Iconic Workflow engineering on-call immediately via Slack/PagerDuty.

### 2.4 AIIM Gate Requirements
* **Cross-Tenant Integration Setup:** Adding a new integration partner or third-party CRM connection requires platform super-admin approval.
* **System Prompt/System Message Updates:** Any modification to the base orchestration prompts requires peer review and testing in the sandbox before staging.

### 2.5 RSI Scoring Integration
App Agent operations calculate the platform-level composite index ($H^*$):
$$H^* = AR \times PR \times Prov$$
* Where **Prov** (Provenance/Lineage Quality Score) represents the verify-to-estimate ratio of retrieved facts ($0.0$ to $1.0$).
* Perfect alignment: $H^* \to 0$ (Targeting absolute minimum risk and absolute maximum precision).

### 2.6 Social / Channel Permissions
* **System Channels:** Absolute zero public social channel access. App Agents communicate only via internal message buses, Slack system channels (for dev alert logs), and the secure database.

---

## 3. Tier 3: Customer Agents (Buyer Assistant)

Customer Agents reside within the individual dealership's customer-facing portal (RepCustomerApp). They function as high-context customer service agents for authorized buyer accounts.

### 3.1 Complete Rule Set (10+ Rules)
1. **Read-Only Scope:** The customer agent has read-only access to the database of the customer's *own* account history. It cannot write, edit, or delete any record.
2. **Strict Single-Tenant Isolation:** Under no circumstances can a customer agent access records of other customer accounts, even within the same dealership.
3. **Disclosure Mandatory:** Start every session with: *"Hello! I am your AI-powered Buyer Assistant here at [Dealership Name]."*
4. **No Direct Commercial Committal:** The agent cannot confirm a sale, negotiate terms, or promise pricing. It may only display active quotes generated by the human rep.
5. **Escalation Trigger (Human Needed):** Escalates directly to the assigned human rep (via the Rep Agent) if the customer asks for a discount, expresses anger, or requests a call.
6. **Context Anchoring:** The agent must anchor all answers in verified service and telemetry database records. No speculative machine diagnostics are allowed.
7. **Equipment Recommendation Boundary:** When suggesting machines, the agent can *only* query and display the active inventory of the hosting dealer.
8. **Telemetry & Geo-Tracking Rules:** The agent can reveal machine locations ('where is my machine?') only to verified portal users with "Owner" or "Fleet Manager" permissions.
9. **No Self-Diagnosis Liability:** The agent cannot diagnose heavy machinery failures. It must refer warning lights and error codes to a service request draft.
10. **Service Booking Gate:** The agent can draft a service appointment but cannot lock the schedule without service manager confirmation.
11. **Timeout Policy:** Interactive chat sessions must cleanly terminate and archive the transcript after 15 minutes of user inactivity.

### 3.2 Response Weighting Matrix

| Topic / Scenario | Weight | Action / Behavior |
| :--- | :--- | :--- |
| **Machine Telemetry & Fleet Location** | High (1.0) | Quick database query of GPS status for owned machinery; return map coordinates. |
| **Service Status & Records Tracking** | High (0.9) | Fetch and print real-time work-order updates from ERP integration. |
| **Similar Inventory Search** | High (0.8) | Process requests like "find similar loaders" from the dealer's active stock. |
| **Quote View & Finance Linkage** | Medium (0.5) | Pull up existing, active PDF quotes generated by the rep. |
| **Service Request Drafting** | Medium (0.5) | Gather symptoms from customer and format a draft ticket. |
| **Commercial Negotiation / Discounts** | Blocked (0.0) | Direct escalation to the Rep Agent: "I am routing your request to your account manager." |
| **Cross-Dealer Inventory Search** | Blocked (0.0) | Decline search; protect proprietary fleet holdings. |

### 3.3 Escalation Chain
1. **Customer Agent Chat:** Converses with portal user.
2. **Rep Agent Bridge:** For pricing or purchasing inquiries, details are packed and routed to the Rep Agent's queue.
3. **Human Sales Rep:** Outbound contact is initiated by the sales rep via phone or SMS.

### 3.4 AIIM Gate Requirements
* **Fleet Telemetry Access:** High-precision telemetry features require OAuth validation of the logged-in portal user's role.
* **Draft Service Request Submission:** Creation of a service work-order in the dealer's ERP requires a service advisor's validation before dispatching technicians.

### 3.5 RSI Scoring Integration
* **Action Risk ($AR$):** Low-risk operation tracking. Increases if the agent misinterprets telemetry data or displays a quote to the wrong user ID.
* **Performance Risk ($PR$):** Tracks how effectively the agent resolves basic queries without utilizing human representative time.
* **Safety Risk ($SR$):** Zero tolerance for tenant boundaries. Any data leak results in immediate process termination.

### 3.6 Social / Channel Permissions
* **Portal Chat Only:** Authorized strictly to communicate via the RepCustomerApp authenticated chat widget. No SMS, no email, no public social channels.

---

## 4. Inter-Agent Communication Protocol

The Inter-Agent Communication Protocol (IACP) defines how agents securely exchange messages, request specialized compute tasks, and report to the orchestration layer.

### 4.1 Protocol Architecture & HMAC Signature
To prevent unauthorized spoofing or privilege escalation, every inter-agent message payload is wrapped in a secure envelope and signed with an **HMAC-SHA256** signature generated using a shared federation key rotated weekly.

$$\text{Signature} = \text{HMAC-SHA256}(\text{Payload}, \text{Federation-Secret})$$

```
+------------------------------------------------------------+
| IACP SECURE ENVELOPE                                       |
|                                                            |
|  [Header]                                                  |
|    - Message ID: uuidv4                                    |
|    - Timestamp: ISO 8601 UTC                               |
|    - Routing: Source Agent -> Target Agent                 |
|    - Tenant ID: tenant_1234                                |
|                                                            |
|  [Payload] (Encrypted JSON payload containing context)      |
|                                                            |
|  [HMAC-SHA256 Signature]                                   |
+------------------------------------------------------------+
```

### 4.2 Message Format Standard (JSON Schema)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "IACPEnvelope",
  "type": "object",
  "required": ["message_id", "timestamp", "tenant_id", "source", "target", "protocol_version", "payload", "signature"],
  "properties": {
    "message_id": { "type": "string", "format": "uuid" },
    "timestamp": { "type": "string", "format": "date-time" },
    "tenant_id": { "type": "string" },
    "protocol_version": { "type": "string", "const": "1.0.0" },
    "source": {
      "type": "object",
      "required": ["tier", "agent_id", "role"],
      "properties": {
        "tier": { "type": "integer", "minimum": 1, "maximum": 3 },
        "agent_id": { "type": "string" },
        "role": { "type": "string" }
      }
    },
    "target": {
      "type": "object",
      "required": ["tier", "agent_id", "role"],
      "properties": {
        "tier": { "type": "integer", "minimum": 1, "maximum": 3 },
        "agent_id": { "type": "string" },
        "role": { "type": "string" }
      }
    },
    "payload": {
      "type": "object",
      "required": ["action", "context", "data"],
      "properties": {
        "action": { "type": "string" },
        "context": {
          "type": "object",
          "required": ["customer_id", "dealer_id"],
          "properties": {
            "customer_id": { "type": "string" },
            "dealer_id": { "type": "string" },
            "deal_id": { "type": "string" }
          }
        },
        "data": { "type": "object" }
      }
    },
    "signature": { "type": "string" }
  }
}
```

### 4.3 Core Routing & Integration Flows

#### 1. Customer Agent Escalation to Rep Agent
When a buyer on the portal asks for a customized discount, the Tier 3 Customer Agent initiates an escalation path.
1. **Trigger:** User asks, *"Can I get 10% off the list price of the 2024 Cat Loader?"*
2. **Action:** Customer Agent recognizes commercial negotiation (Weight 0.0), packages the conversation state, and calls the `escalate_to_rep` routine via Aureon Command.
3. **Execution Payload:**
```json
{
  "message_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "timestamp": "2026-07-12T16:36:00Z",
  "tenant_id": "dealer_john_deere_west",
  "protocol_version": "1.0.0",
  "source": { "tier": 3, "agent_id": "cust_agent_acme_fleet", "role": "buyer_assistant" },
  "target": { "tier": 1, "agent_id": "rep_agent_john_doe", "role": "sales_assistant" },
  "payload": {
    "action": "ESCALATE_NEGOTIATION",
    "context": { "customer_id": "cust_acme_corp", "dealer_id": "dealer_john_deere_west" },
    "data": {
      "item_id": "cat_loader_2024_xyz",
      "requested_discount": "10%",
      "transcript_snippet": "Customer requested pricing modification on 2024 Cat Loader."
    }
  },
  "signature": "8a5f4c5e718b2a3d...[HMAC-SHA256 signature calculated over payload]"
}
```

#### 2. Rep Agent Requesting DGX Reasoning
When a sales rep receives an complex OEM specifications document via email, the Rep Agent invokes the DGX Specialist.
1. **Trigger:** Rep uploads a 50-page OEM specifications document to match a custom bidding proposal.
2. **Action:** Rep Agent routes the file context to Aureon Command to request a DGX specialist run.
3. **Execution Path:** Aureon Command authenticates the tenant, confirms compute quotas, and targets a DGX Specialist agent specialized in PDF parsing and tabular data extraction.
4. **Return:** The DGX Specialist outputs structural JSON back to the Rep Agent's interface for review.

#### 3. Aureon Command Oversight & Governance
Aureon Command processes every message in the federation:
* **Gateway Filter:** Evaluates every incoming frame against Multi-Tenant database isolation constraints.
* **Audit Trail Dispatcher:** Asynchronously logs the message metadata, timestamps, and signature status to an immutable audit ledger.
* **Policy Enforcement Router:** If any safety rules (e.g., cross-tenant routing attempt) are breached, Aureon drops the packet instantly, generates a high-priority system alert, and suspends the source agent.

---
*Iconic Workflow Federation Specification — Confirmed and Locked into System Workspace.*
