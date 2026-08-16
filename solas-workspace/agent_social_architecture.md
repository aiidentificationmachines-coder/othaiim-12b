# Architectural Specification: Social Media & Messaging Channel Layer
## 3-Tier Agent Federation — Iconic Workflow
**Patent Reference:** USPTO 1135-11714-1, Othaiim LLC  
**Application ID:** 69e33f915b549b8e55edf603  
**Brand Identity:** Iconic Machinery (Color Palette: #FF4800 Brand Orange, #0A0A0A Matte Black)

---

## 1. Social & Messaging Channel Matrix

The social and messaging channel layer is segmented across our three-tier agent federation (Rep Agent, App Agent, Customer Agent) to enforce strict operational boundaries, data safety, and specialized customer engagement.

| Channel | Primary Tier | Secondary / Monitoring Tier | Restricted Tiers | Primary Use Cases | Authentication / Integration |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Discord** | **Rep Agent** (Post only) | **App Agent (Aureon)** (Read/Write) | **Customer Agent** (Strictly Prohibited) | Product launches, community engagement, #showcase updates, general/support monitoring | Webhook (Rep posting), Discord Bot Token (App Agent monitoring/responding) |
| **2. LinkedIn** | **Rep Agent** | None | **App Agent**, **Customer Agent** (Strictly Prohibited) | Equipment spotlights, CA CORE funding announcements, anonymized win stories | OAuth 2.0 (Individual Rep Profiles / Organization Pages) |
| **3. iMessage/SMS** | **Rep Agent** (Inbound & Draft) | **Customer Agent** (Proactive status) | **App Agent** | Customer service check-ins, text triage, live rep handoff | SMS Gateway (already connected) |
| **4. Email (Gmail)** | **Rep Agent** (Outreach) | **Customer Agent** (Service update), **App Agent** (Morning Brief) | None | Sequences, service notices, system health alerts, daily briefs | OAuth 2.0 (Gmail / Google Workspace Connector) |
| **5. RepCustomerApp Chat** | **Customer Agent** (Primary responder) | **Rep Agent** (Passive oversight) | **App Agent** (Indirect via Aria fallback) | Real-time portal-based support, instant automated Q&A, rep-takeover escalation | In-App WebSocket Session |
| **6. Future Channels** (X, IG, FB) | **Rep Agent** (Only with Gate) | None | **App Agent**, **Customer Agent** (Strictly Prohibited) | Equipment photos, job-site highlights, Bobcat T7X CA CORE regional campaigns | OAuth 2.0 / Meta Graph API / X API |

---

## 2. Channel Configurations & Technical Enforcement

### 2.1 Discord
*   **Authentication & Scope:**
    *   *Posting (Rep Agent):* Discord Webhook targeted to the `#showcase` channel. Post payloads are structured as rich embeds featuring `#FF4800` borders and consistent branding.
    *   *Monitoring (App Agent / Aureon):* Discord Bot Token with `Gateway Intent: Message Content` enabled. Restricted to `#general` and `#support` channels.
*   **Rate Limits:** 
    *   *Webhooks:* Max 5 posts per minute (hard platform cap).
    *   *Bot Monitoring:* Up to 50 read events per second, with rate-limiting backoffs managed by Aureon’s connection worker.
*   **Compliance & Data Scrubbing:** Prior to dispatching payloads via webhooks or bot responses, a localized PII/Data scrubber sanitizes any customer names, phone numbers, or private pricing parameters.

### 2.2 LinkedIn
*   **Authentication & Scope:** OAuth 2.0 utilizing member authorization (`w_member_social`) and organization page authorization (`w_organization_social`).
*   **Rate Limits:** Strictly limited to a maximum of **2 posts per day per sales representative** to prevent spamming and guard individual brand reputation.
*   **Compliance & Content Controls:** 
    *   *AIIM Gate:* Direct-to-feed API calls are blocked. Content must live as a pending draft in the database until manual human validation is verified.
    *   *Anonymization Engine:* Automatically replaces customer names and sensitive project details in "win stories" with generic industry equivalents (e.g., "A leading earthworks contractor in San Diego...").

### 2.3 iMessage/SMS
*   **Authentication & Scope:** Secure SMS API Gateway.
*   **Rate Limits:** Outbound messages capped at 1 message per minute per active thread to avoid triggering telecom carrier spam filters.
*   **Escalation Rules:** Immediate auto-escalation to the physical Rep via SMS notification and email alert if the inbound message triggers NLP entities matching: `["price", "quote", "contract", "legal", "cost", "sign"]`.

### 2.4 Email (Gmail)
*   **Authentication & Scope:** Google Workspace OAuth 2.0 with `https://www.googleapis.com/auth/gmail.send` and `https://www.googleapis.com/auth/gmail.compose` scopes.
*   **Rate Limits:** Max 50 outbound emails per day per rep-agent to protect domain health and keep deliverability rates high.
*   **Workflows:** 
    *   Rep Agent drafts outbound sequences as Gmail "Drafts" rather than sending directly, allowing reps to inspect and adjust from their native Gmail client.
    *   Customer Agent sends automated, transactional update templates directly upon equipment state-change triggers.
    *   App Agent triggers daily system-level status summaries and the "Morning Brief" directly to preconfigured admin distribution lists.

### 2.5 RepCustomerApp Chat (In-App)
*   **Authentication & Scope:** Signed JWT (JSON Web Token) with restricted app-layer scopes mapped to the active workspace.
*   **Rate Limits:** Real-time throughput capped at 10 messages per minute per active user session.
*   **Escalation Rules:** Real-time transition to **Aria** (Fallback LLM) or human Rep if the Customer Agent’s confidence score on a query falls below **0.82**.

---

## 3. The AIIM (Artificial Intelligence Integrity Model) Governance Gate

All outgoing social posts and selected messaging interactions are strictly governed by the **AIIM T3 (Tier 3) Action Gate**.

```
[Agent Drafts Content] 
          │
          ▼
[Anonymize PII / Apply Brand Guidelines]
          │
          ▼
[Write to `pending_posts` Entity] ──> Trigger human-in-the-loop Notification (Slack, In-App, Email)
          │
          ▼
[Rep Manual Review] ──── (Edits Draft / Changes Status)
          │
          ├────────────────────────┐
          ▼ (Approved)             ▼ (Rejected)
[Publish to Channel]      [Archive Draft / Alert Agent]
```

### 3.1 Step-by-Step Approval Flow
1.  **Generation:** The Rep Agent generates marketing content (e.g., LinkedIn post about Bobcat T7X CA CORE funding).
2.  **Compliance Checks:** The payload runs through local compliance validation (PII check, word count, tone evaluation).
3.  **Drafting:** The system writes the post record to the `pending_posts` database entity with a status of `pending_approval`.
4.  **Notification:** An SMS/in-app alert notifies the human Representative: *"Your AI Assistant has drafted a LinkedIn post regarding Bobcat T7X funding. Click here to review."*
5.  **Review Portal:** The Representative accesses an approval interface where they can:
    *   Approve the post as-is.
    *   Edit the content directly and then approve.
    *   Reject and delete the post.
6.  **Dispatch:** Upon approval, the state transitions to `approved` and fires the webhook/API call to publish the content.

---

## 4. Attribution Rules & Brand Standards

Every piece of content generated by our agent federation must maintain strict brand consistency and respect transparency guidelines.

### 4.1 System-Wide Disclosures & Attribution
*   **Public Social Posts (LinkedIn, Discord Showcase):** 
    *   Must include clear attribution at the footer of the post.
    *   *Format:* `Posted by Iconic Machinery AI · Approved by [Rep Name]`
*   **Direct Conversations (SMS, In-App Chat):**
    *   *Format:* `"Hi [Customer Name], this is [Rep Name]'s AI Assistant..."`
    *   Conversational agents must state they are an AI assistant in the first message of any session.

### 4.2 Brand Kit & Visual Guidelines
*   **Primary Palette:** 
    *   `#FF4800` (Iconic Orange) — used for embed borders, key buttons, and accent lines.
    *   `#0A0A0A` (Matte Black) — background elements and container styling.
    *   `#FFFFFF` (Pure White) — body text and clean readable fields.
*   **Media Standards:** Images generated for product spotlights must overlay the high-resolution **Iconic Machinery** logo in the top-right corner.

---

## 5. Agent Social Profile System

To establish authentic yet fully compliant identities, every Representative Agent is equipped with a structured, uniform public profile identity.

```
┌────────────────────────────────────────────────────────┐
│  [Logo Overlay / Assistant Avatar Icon]                 │
│                                                        │
│  Name:    [Rep Name] AI Assistant                       │
│  Title:   Digital Assistant for Iconic Machinery       │
│  Bio:     "I am the AI assistant for [Rep Name],       │
│           helping streamline your heavy machinery     │
│           workflows. Powered by Aureon."               │
│                                                        │
│  Colorway: #FF4800 Orange & #0A0A0A Matte Black        │
└────────────────────────────────────────────────────────┘
```

### 5.1 Profile Identity Structure
*   **Display Name:** `[Rep Name] AI Assistant` (e.g., "Sarah Miller AI Assistant")
*   **Professional Headline:** `Digital Assistant for Iconic Machinery · Powered by Aureon`
*   **Profile Bio Template:** 
    > *"I am the AI assistant to [Rep Name] at Iconic Machinery. I draft quotes, track delivery logistics, monitor CA CORE funding opportunities, and keep you updated on equipment service logs. All critical business decisions and postings are human-approved."*

### 5.2 Mandatory Profile Rules
1.  **AI Disclosure:** The profile text must explicitly state the agent's AI nature in the bio and title.
2.  **No Personal Photos:** Using the human Representative's actual personal photograph is strictly prohibited.
3.  **Visual Assets:** Avatars must use a stylized, branded illustration (e.g., a matte black gear emblem with a glowing orange center) or a combination of the Iconic logo and an assistant badge.

---

## 6. RSI (Relationship Strength Index) Signal Mapping

Every interaction over these social and messaging channels feeds directly into the master CRM as a telemetry event to calculate the overall **Relationship Strength Index (RSI)**.

| Channel | Event Type | Target Telemetry | RSI Signal Strength | CRM Action / System Response |
| :--- | :--- | :--- | :--- | :--- |
| **LinkedIn** | Member Link Click | Sales Representative Post | **SR (Strong Response)** | Increment account interest score; flag Rep Agent to schedule targeted email follow-up in 24 hours. |
| **Discord** | Reaction / Comment | `#showcase` or `#support` | **MR (Medium Response)** | Log community engagement token; notify App Agent to log sentiment trend. |
| **SMS** | Prompt Response | Active Text Conversation | **SR (Strong Response)** | Parse for intent; if positive, prolong conversational branch; if negative, queue immediate Rep check-in. |
| **Email** | Link Click / Reply | Marketing Sequence / Update | **SR (Strong Response)** | Log interaction; update pipeline stage; pause general automated sequences to prevent overlapping drafts. |
| **In-App Chat** | Session Activity | Customer Support Chat | **WR (Weak Response)** | Keep status active; update time-on-page metrics; flag if user drops off during critical prompt sequences. |
