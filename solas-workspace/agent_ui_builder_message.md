# 'My AI Assistant' Builder Message & Entity Schemas

## 1. Builder Message (.agents/agent_ui_builder_message.md)

```markdown
# Iconic Workflow: 'My AI Assistant' Page Specifications

## Page Configuration
- **Route**: `/my-ai-assistant`
- **Theme**: Dark theme only. Background: `#0A0A0A`, Accents: `#FF4800` (Orange), Surface cards: `#161616`, Borders: `#262626`, Text primary: `#FFFFFF`, Secondary: `#A3A3A3`.
- **Targeting**: Field-first, 100% mobile-friendly responsive layouts with touch-friendly tap targets.

---

## Page Layout & Component Specs

### TOP SECTION: AGENT IDENTITY CARD (Grid / Flexbox header)
- **Title**: Dynamic heading `[Rep Name]'s AI` using `AgentProfile.data.agent_name` (fallback: `[Rep Name]'s AI`).
- **Status Badge**: Inline chip colored dynamically by `AgentProfile.data.status`:
  - `ACTIVE` (green badge, `#10B981`)
  - `LEARNING` (blue badge, `#3B82F6`)
  - `CALIBRATING` (orange badge, `#FF4800`)
- **RSI Score Gauges**: Three radial/circular visual gauges representing:
  - **Approval Rate (AR)**: `AgentProfile.data.rsi_ar` %
  - **Performance Rate (PR)**: `AgentProfile.data.rsi_pr` %
  - **Success Rate (SR)**: `AgentProfile.data.rsi_sr` %
- **Metrics**: Card showing "Total interactions this month: `AgentProfile.data.monthly_interactions`".
- **CTA**: "Train My Agent" Button (outlined orange variant). Opens a sliding side drawer or modal displaying recent negative RSI signals with rating slider (1-5 stars) to correct and refine prompt weights.

### SECTION A: QUICK ACTIONS (Responsive 2x3 Grid, stack to 1-col on mobile)
Each card features an icon, a title, a short helper text, and triggers an overlay wizard.
1. **'Draft Customer Outreach'**: Prompts rep to select a customer (from `Customer` entity), queries AI to draft a personalized email/text based on relationship status.
2. **'Post to LinkedIn'**: AI drafts an equipment spotlight post about selected inventory. Rep reviews/approves directly to schedule social share.
3. **'Follow Up on Quotes'**: Lists stale quotes (under 7 days old, status: Sent). AI drafts direct follow-up message ready to send.
4. **'Answer Customer Question'**: Input textbox. Rep types a technical/logistics question; AI generates response using local product manual embeddings.
5. **'Generate Equipment Spotlight'**: Dynamic machine picker. AI writes tailored social and email marketing copy.
6. **'Check My Pipeline'**: Single-tap generation. Summarizes open opportunities and outputs actionable "Next Steps" bullets.

### SECTION B: PENDING APPROVALS (Card List)
Displays filtered records from `AgentAction` where `status = "PENDING"`.
- **Row Structure**: 
  - Left: Channel badge (LinkedIn: `#0077B5`, Email: `#D44638`, SMS: `#10B981`) & Target Customer Name.
  - Middle: Expandable body text snippet of the generated draft.
  - Right (Buttons stacked on mobile): 
    - **Approve (Orange)**: Updates status to `"APPROVED"`, triggers workflow to send/post instantly.
    - **Edit (Grey)**: Opens inline textarea to modify draft before approving.
    - **Reject (Red)**: Updates status to `"REJECTED"`, triggers prompt to select a reason (Too technical / Wrong tone / Inaccurate stats), creating negative RSI penalty.

### SECTION C: OUTREACH CAMPAIGN MANAGER
- **Active Campaigns Table/Cards** (`AgentCampaign` records):
  - Displays: Campaign Name, Target Count, Sent Count, Response Rate, and "AI Confidence Score".
  - **CTA**: "New Campaign" button opens a step-by-step creation wizard:
    1. Select Target Audience Segment (e.g., California Scrap Yards).
    2. Define Goal & AI Persona.
    3. Generate sequence (AI auto-builds 3-step schedule).
    4. Approve & Launch. Successful responses post positive PR signals back to RSI database.

### SECTION D: CUSTOMER AGENT MONITOR (Real-time Session Viewer)
- Lists active sessions from `CustomerAgentSession` where `assigned_rep_id` matches current user.
- **Indicators**:
  - Customer Name, Last Interaction timestamp, detected Core Topic.
  - **Escalation Badge**: High visibility red pulse indicator if `escalation_status = "ESCALATED"`.
- **Interactions**:
  - "View Conversation" button opens chat-log interface detailing chronological AI-to-Customer messages.
  - "Take Over / Respond" button pauses the automated AI model for that session, setting `escalation_status = "RESOLVED"` and opening direct rep-to-customer chat bridge.

### SECTION E: MY AGENT SETTINGS (Two-column layout, stacks on mobile)
Saves parameters back to `AgentProfile`:
- **Agent Name Input**: Simple text input (updates header dynamically).
- **Tone Select**: Radio button grid (Professional, Friendly, Technical, Consultative).
- **Auto-Approve Threshold Slider**: Ranges from 50% to 100%. If AI confidence matches/exceeds, skips pending approval queue and auto-sends.
- **Channel Toggles**: Individual switch toggles for LinkedIn, Email, and SMS integrations.
- **Off-Hours Auto-Response**: Toggle + time windows. Delays/queues out-of-bound responses automatically.
- **Danger Zone**: "Reset My Agent" red button. Wipes system instruction tweaks/parameters, logs a reset audit, but preserves historical RSI metrics to prevent model regression.

### SECTION F: AGENT ACTIVITY LOG (Paginated List)
- Chronological timeline of records from `AgentAction` with statuses `"APPROVED"`, `"REJECTED"`, `"AUTO-SENT"`.
- Shows time, detailed action string, target channel, output status, and the resulting RSI score delta (e.g., `+0.2% AR`).
- Filter toolbar at top: segmented pill buttons for `All`, `Approved`, `Rejected`, `Pending`, and `Auto-Sent`.
```

---

## 2. Entity Schemas

### Entity 1: `AgentProfile`
Stores the configuration, metadata, parameters, and live performance metrics for each sales representative's specific AI agent.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentProfile",
  "type": "object",
  "properties": {
    "rep_id": {
      "type": "string",
      "description": "Unique identifier of the sales representative who owns this agent."
    },
    "agent_name": {
      "type": "string",
      "description": "Custom personalized name for the AI agent (e.g., 'Sarah's Assistant')."
    },
    "status": {
      "type": "string",
      "enum": ["ACTIVE", "LEARNING", "CALIBRATING"],
      "description": "Current system operating status of the agent."
    },
    "rsi_ar": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Approval Rate: Percentage of AI drafts approved without major revision."
    },
    "rsi_pr": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Performance Rate: Engagement, click-through, and response rate performance metric."
    },
    "rsi_sr": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Success Rate: Conversion rate of AI-driven touchpoints to won deals."
    },
    "monthly_interactions": {
      "type": "integer",
      "minimum": 0,
      "description": "Count of successful interactions or actions taken this calendar month."
    },
    "tone": {
      "type": "string",
      "enum": ["Professional", "Friendly", "Technical", "Consultative"],
      "description": "The personality archetype driving AI content generation and conversations."
    },
    "auto_approve_threshold": {
      "type": "integer",
      "minimum": 50,
      "maximum": 100,
      "description": "Confidence percentage threshold above which the agent can post or email without approval."
    },
    "channels": {
      "type": "object",
      "properties": {
        "linkedin_enabled": { "type": "boolean" },
        "email_enabled": { "type": "boolean" },
        "sms_enabled": { "type": "boolean" }
      },
      "required": ["linkedin_enabled", "email_enabled", "sms_enabled"]
    },
    "off_hours_enabled": {
      "type": "boolean",
      "description": "If true, queues messages outside working hours or sends a delayed notification auto-reply."
    }
  },
  "required": ["rep_id", "agent_name", "status", "rsi_ar", "rsi_pr", "rsi_sr", "tone", "auto_approve_threshold", "channels"]
}
```

### Entity 2: `AgentAction`
Logs every action, generation, approval cycle, and messaging attempt processed by the representative's agent.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentAction",
  "type": "object",
  "properties": {
    "action_id": {
      "type": "string",
      "description": "Unique transaction ID."
    },
    "rep_id": {
      "type": "string",
      "description": "ID of the agent's owner."
    },
    "action_type": {
      "type": "string",
      "enum": ["OUTREACH_DRAFT", "LINKEDIN_POST", "QUOTE_FOLLOW_UP", "CUSTOMER_ANSWER", "SPOTLIGHT_GEN", "PIPELINE_CHECK"],
      "description": "The category of quick action or automated activity executed."
    },
    "channel": {
      "type": "string",
      "enum": ["LinkedIn", "Email", "SMS", "System"],
      "description": "Target publishing and execution channel."
    },
    "customer_id": {
      "type": "string",
      "description": "Target customer ID, if applicable."
    },
    "content_preview": {
      "type": "string",
      "description": "The generated marketing copy, draft response, or outreach body text."
    },
    "status": {
      "type": "string",
      "enum": ["PENDING", "APPROVED", "REJECTED", "AUTO_SENT"],
      "description": "Workflow progression status of this content block."
    },
    "confidence_score": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "AI model evaluation confidence percentage."
    },
    "rsi_delta": {
      "type": "number",
      "description": "The performance feedback score adjustment generated by this decision (e.g., -1.5, +0.5)."
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": ["action_id", "rep_id", "action_type", "channel", "content_preview", "status", "confidence_score", "timestamp"]
}
```

### Entity 3: `AgentCampaign`
Represents scheduled, active, or completed mass outreach pipelines crafted and calibrated by the assistant.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentCampaign",
  "type": "object",
  "properties": {
    "campaign_id": {
      "type": "string",
      "description": "Unique tracking key."
    },
    "rep_id": {
      "type": "string",
      "description": "The creator/representative managing this sequence."
    },
    "name": {
      "type": "string",
      "description": "Descriptive name of the outreach segment campaign."
    },
    "target_segment": {
      "type": "string",
      "description": "Criteria or name of the audience subset (e.g., 'CA Core T7X Yards')."
    },
    "target_count": {
      "type": "integer",
      "minimum": 0,
      "description": "Total records targeted in this batch."
    },
    "sent_count": {
      "type": "integer",
      "minimum": 0,
      "description": "Number of outreach iterations dispatched so far."
    },
    "response_rate": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Percentage of outbound dispatches resulting in customer reply."
    },
    "ai_confidence_score": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Estimated success rating computed prior to kickoff."
    },
    "status": {
      "type": "string",
      "enum": ["DRAFT", "ACTIVE", "PAUSED", "COMPLETED"]
    }
  },
  "required": ["campaign_id", "rep_id", "name", "target_segment", "target_count", "sent_count", "response_rate", "ai_confidence_score", "status"]
}
```

### Entity 4: `CustomerAgentSession`
Tracks independent conversations that direct customer-facing AI agents are having with clients, which the rep can monitor and intercept.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CustomerAgentSession",
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Unique conversation reference token."
    },
    "customer_id": {
      "type": "string",
      "description": "ID of the customer engaging with the agent."
    },
    "customer_name": {
      "type": "string",
      "description": "Cached display name of the customer for immediate render speed."
    },
    "assigned_rep_id": {
      "type": "string",
      "description": "ID of the rep responsible for monitoring this conversation."
    },
    "last_interaction": {
      "type": "string",
      "format": "date-time",
      "description": "Timestamp of the last message sent inside this session."
    },
    "topic": {
      "type": "string",
      "description": "Primary detected topic extracted by AI classification."
    },
    "escalation_status": {
      "type": "string",
      "enum": ["MONITORING", "ESCALATED", "RESOLVED"],
      "description": "Flags conversations requiring manual representative takeover."
    },
    "chat_history": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "sender": { "type": "string", "enum": ["CUSTOMER", "AI_AGENT", "REPRESENTATIVE"] },
          "message": { "type": "string" },
          "timestamp": { "type": "string", "format": "date-time" }
        },
        "required": ["sender", "message", "timestamp"]
      }
    }
  },
  "required": ["session_id", "customer_id", "customer_name", "assigned_rep_id", "last_interaction", "topic", "escalation_status", "chat_history"]
}
```
