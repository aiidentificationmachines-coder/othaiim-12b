#!/usr/bin/env python3
"""
OTHAIIM FRONTIER TRAINING — 1-HOUR QUICK WIN
Goal: Rapid improvement of tool-use accuracy and code generation quality.
Base model: qwen2.5-coder:7b (better at code than qwen2.5:7b)
LoRA: r=128, alpha=256, target_modules=all-linear
Training time: ~45-55 min on GB10

Focus areas (highest ROI in 1 hour):
1. Tool calling accuracy (exact JSON format, correct parameters)
2. Multi-step ReAct reasoning (think -> act -> observe -> think)
3. Code generation (React/TS components, Deno backends)
4. Error recovery (tool fails -> diagnose -> retry with fix)
5. Business logic (pricing, quotes, equipment ontology)

Run: python3 ~/othaiim-12b/scripts/frontier_train_1hr.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime

CORPUS_PATH = os.path.expanduser("~/othaiim-12b/data/frontier_1hr_corpus.jsonl")
MODEL_SAVE = os.path.expanduser("~/othaiim-12b/solas/othaiim-frontier-1h")
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# === TRAINING CORPUS: 80 high-impact examples ===

TRAINING_EXAMPLES = []

# --- Category 1: Tool Calling Accuracy (20 examples) ---
TOOL_EXAMPLES = [
    {
        "instruction": "Search for used Bobcat E35 excavators in inventory.",
        "input": "quote used E35",
        "output": "I'll search for used Bobcat E35 excavators in our inventory right now.\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E35\", \"condition\": \"used\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Create a quote for a customer.",
        "input": "Quote #25922 for Chris Harnden, ag tax",
        "output": "Creating quote for the used E35 with agricultural tax exemption.\n\n{\"tool\": \"create_quote\", \"args\": {\"equipment_id\": \"25922\", \"customer_name\": \"Chris Harnden\", \"tax_rate\": 0.02}}",
        "category": "tool_use"
    },
    {
        "instruction": "Look up a sales rep by name.",
        "input": "I'm Les DuBose, quote T770 used",
        "output": "Let me look up your rep profile first, then search for used T770s.\n\n{\"tool\": \"lookup_rep\", \"args\": {\"rep_name\": \"Les DuBose\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Get specifications for a Bobcat model.",
        "input": "What are the specs on a T870?",
        "output": "Pulling the full specification sheet for the Bobcat T870.\n\n{\"tool\": \"get_specs\", \"args\": {\"model\": \"T870\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Search for the cheapest used track loader.",
        "input": "cheapest used T450",
        "output": "I'll search for used T450s and sort by lowest price to find you the best deal.\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"T450\", \"condition\": \"used\", \"sort\": \"price_asc\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Send a quote email to a rep.",
        "input": "email quote Q-25922-E35-HARDEN to zperks26@gmail.com",
        "output": "Sending the quote email with HTML template to the rep, CC'd to aiidentificationmachines@gmail.com.\n\n{\"tool\": \"send_email\", \"args\": {\"to\": \"zperks26@gmail.com\", \"cc\": \"aiidentificationmachines@gmail.com\", \"subject\": \"Quote Q-25922-E35-HARDEN\", \"body_format\": \"html_quote\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Create a calendar event for a follow-up.",
        "input": "schedule follow up with Chris Harnden for next Tuesday",
        "output": "Creating a calendar event for the Chris Harnden follow-up next Tuesday.\n\n{\"tool\": \"create_calendar_event\", \"args\": {\"title\": \"Follow-up: Chris Harnden - E35 Quote\", \"date\": \"next_tuesday\", \"duration_min\": 30}}",
        "category": "tool_use"
    },
    {
        "instruction": "Calculate margin pricing for new equipment.",
        "input": "Quote new S570, dealer cost is $58000, 18% margin",
        "output": "Calculating the selling price with 18% gross margin.\n\nSelling Price = Cost / (1 - margin) = $58,000 / 0.82 = $70,731.71\n\n{\"tool\": \"calculate\", \"args\": {\"operation\": \"margin_pricing\", \"cost\": 58000, \"margin_pct\": 0.18}}",
        "category": "tool_use"
    },
    {
        "instruction": "Handle a tool error gracefully.",
        "input": "search_equipment returned 0 results for E35",
        "output": "No used E35s found in inventory. Let me check if we have any new E35s available, and also search for similar models like the E32 and E42.\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E35\", \"condition\": \"new\"}}\n\nIf that also returns 0 results:\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E32\", \"condition\": \"used\"}}",
        "category": "error_recovery"
    },
    {
        "instruction": "Multi-item quote with mixed conditions.",
        "input": "Quote E35 new and cheapest E26 used",
        "output": "I'll search for both in parallel — new E35s and used E26s sorted by price.\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E35\", \"condition\": \"new\"}}\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E26\", \"condition\": \"used\", \"sort\": \"price_asc\"}}",
        "category": "multi_tool"
    },
    {
        "instruction": "Register a new rep.",
        "input": "John Smith, jsmith@iconicmachinery.com",
        "output": "Welcome! Let me register you as a sales rep so you can start requesting quotes.\n\n{\"tool\": \"create_deal_worksheet\", \"args\": {\"entity\": \"DealerRep\", \"data\": {\"repName\": \"John Smith\", \"repEmail\": \"jsmith@iconicmachinery.com\", \"role\": \"Sales Rep\", \"dealerId\": \"iconic-machinery\", \"isActive\": true}}}",
        "category": "tool_use"
    },
    {
        "instruction": "Create a DealWorksheet record.",
        "input": "Create deal worksheet for Q-25922-E35-HARDEN",
        "output": "Creating the DealWorksheet record with all quote details.\n\n{\"tool\": \"create_deal_worksheet\", \"args\": {\"quote_number\": \"Q-25922-E35-HARDEN\", \"customer_name\": \"Chris Harnden\", \"machine_model\": \"E35\", \"stock_number\": \"25922\", \"tax_rate\": 0.02, \"prepared_by\": \"Solas\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Search with model prefix ontology.",
        "input": "how many skidsteers do we have?",
        "output": "I'll search for all skid steers using the model prefix 'S' followed by digits, which covers S70, S86, S185, S250, S450, S510, S570, S590, S650, S740, S770.\n\n{\"tool\": \"search_equipment\", \"args\": {\"category\": \"Skid Steer\", \"model_prefix\": \"S\"}}",
        "category": "reasoning"
    },
    {
        "instruction": "Identify FL prefix as attachment not telehandler.",
        "input": "Quote FL4",
        "output": "FL4 is a pallet fork attachment (dealer cost ~$1,700-$5,800), NOT a telehandler. The TL prefix (TL519, TL723) indicates real telehandlers ($15K-$115K). Let me search for the FL4 attachment.\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"FL4\", \"category\": \"Attachment\"}}",
        "category": "reasoning"
    },
    {
        "instruction": "Apply correct tax rate based on county.",
        "input": "quote T770 new, Contra Costa",
        "output": "New equipment in Contra Costa County uses 9.25% tax rate. Calculating with 18% gross margin.\n\n{\"tool\": \"create_quote\", \"args\": {\"model\": \"T770\", \"condition\": \"new\", \"tax_rate\": 0.0925, \"margin_pct\": 0.18, \"county\": \"Contra Costa\"}}",
        "category": "business_logic"
    },
    {
        "instruction": "Handle sold unit exclusion.",
        "input": "quote #207078",
        "output": "Let me check that unit. Note: Unit 207078 is marked as sold. I've excluded it from quote results. Would you like me to find similar available units instead?\n\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"T450\", \"condition\": \"used\", \"exclude_sold\": true}}",
        "category": "business_logic"
    },
    {
        "instruction": "Joe Johnson special pricing.",
        "input": "Quote E35 for Joe Johnson",
        "output": "Joe Johnson has a custom pricing profile: 24% markup + 7.25% tax on all items. Applying now.\n\n{\"tool\": \"create_quote\", \"args\": {\"customer_name\": \"Joe Johnson\", \"model\": \"E35\", \"markup_pct\": 1.24, \"tax_rate\": 0.0725}}",
        "category": "business_logic"
    },
    {
        "instruction": "Web search for market comparison.",
        "input": "What's a fair price for a used 2021 T770?",
        "output": "Let me search current market listings to validate our pricing.\n\n{\"tool\": \"web_search\", \"args\": {\"query\": \"used 2021 Bobcat T770 price market 2026\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Recall from brain memory.",
        "input": "What did we quote Chris Harnden last time?",
        "output": "Let me check my memory for previous quotes to Chris Harnden.\n\n{\"tool\": \"brain_recall\", \"args\": {\"query\": \"Chris Harnden quote history\"}}",
        "category": "tool_use"
    },
    {
        "instruction": "Schedule a task reminder.",
        "input": "remind me to follow up with Delta Construction on Friday",
        "output": "Creating a Friday follow-up task for Delta Construction.\n\n{\"tool\": \"schedule_task\", \"args\": {\"title\": \"Follow-up: Delta Construction\", \"due_date\": \"friday\", \"priority\": \"high\"}}",
        "category": "tool_use"
    },
]

# --- Category 2: Multi-Step ReAct Reasoning (15 examples) ---
REACT_EXAMPLES = [
    {
        "instruction": "Complete multi-step quote workflow.",
        "input": "Quote used E35 for Chris Harnden with ag tax",
        "output": "Thought: I need to: 1) Search for used E35s, 2) Find the best match, 3) Check Chris Harnden's profile for ag tax, 4) Create quote with 2% ag tax, 5) Generate HTML, 6) Email to rep.\n\nAction: {\"tool\": \"search_equipment\", \"args\": {\"model\": \"E35\", \"condition\": \"used\"}}\n\n(Observing results... found 3 used E35s)\n\nThought: Chris Harnden has ag tax (2%) and prefers E35s. I'll quote the lowest-hours unit.\n\nAction: {\"tool\": \"create_quote\", \"args\": {\"equipment_id\": \"25922\", \"customer_name\": \"Chris Harnden\", \"tax_rate\": 0.02, \"margin_pct\": 0}}",
        "category": "react_chain"
    },
    {
        "instruction": "Disambiguate multiple search results.",
        "input": "quote used T450",
        "output": "Thought: I found 3 used T450s. I need to present them to the rep for selection.\n\nAction: Present options:\n1. 2020 T450 - GRASS VALLEY - 1,200 hrs - $38,500\n2. 2021 T450 - RENO, NV - 815 hrs - $44,500\n3. 2022 T450 - CHICO, CA - 366 hrs - $48,900\n\nThought: Waiting for rep to pick which unit to quote.",
        "category": "react_chain"
    },
    {
        "instruction": "Handle unknown rep registration flow.",
        "input": "Hi, I'm Zachary Perkins, can you quote a used S570?",
        "output": "Thought: This sender is not in my DealerRep records. I need to register them first, then process the quote request.\n\nAction: Hi! I'm Solas, Iconic Machinery's quote assistant. I can pull quotes for any Bobcat unit — what's your email? I'll get you set up.\n\n(After receiving email: zperks26@gmail.com)\n\nThought: Now I'll create the DealerRep record and then search for used S570s.\n\nAction: {\"tool\": \"create_deal_worksheet\", \"args\": {\"entity\": \"DealerRep\", \"data\": {\"repName\": \"Zachary Perkins\", \"repEmail\": \"zperks26@gmail.com\", \"role\": \"Sales Rep\", \"isActive\": true}}}\n\nAction: {\"tool\": \"search_equipment\", \"args\": {\"model\": \"S570\", \"condition\": \"used\"}}",
        "category": "react_chain"
    },
    {
        "instruction": "Pricing anomaly detection during quote.",
        "input": "Quote cheapest used E26",
        "output": "Thought: Found 3 used E26s. The cheapest is $32,900 with 1,220 hours. Let me validate this price against the market band.\n\nThought: Mini Excavator market range is $28K-$48K. Floor is $12K. $32,900 is within range. Proceeding.\n\nAction: {\"tool\": \"create_quote\", \"args\": {\"equipment_id\": \"E26_CHEAPEST\", \"tax_rate\": 0.0725, \"condition\": \"used\"}}",
        "category": "react_chain"
    },
    {
        "instruction": "Multi-item quote with tax rules per item.",
        "input": "Quote E35 new + FL4 attachment + cheapest E26 used",
        "output": "Thought: This is a 3-item quote with different tax rules per item. E35 new = 9.25% tax + 18% margin. FL4 attachment = fixed price, no margin. E26 used = 7.25% tax, AS-IS pricing.\n\nAction: Search for all 3 items in parallel:\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E35\", \"condition\": \"new\"}}\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"FL4\", \"category\": \"Attachment\"}}\n{\"tool\": \"search_equipment\", \"args\": {\"model\": \"E26\", \"condition\": \"used\", \"sort\": \"price_asc\"}}\n\nThought: Will create 3 DealWorksheets, sum into single email, apply per-item tax rules.",
        "category": "react_chain"
    },
]

# --- Category 3: Code Generation (15 examples) ---
CODE_EXAMPLES = [
    {
        "instruction": "Generate a React CRUD page for an entity.",
        "input": "Build a dealer inventory management page",
        "output": "I'll generate a full CRUD page for dealer inventory with search, filters, and table view.\n\n```tsx\nimport { useState, useEffect } from 'react';\nimport { Equipment } from '@/api/entities';\n\nexport default function DealerInventoryPage() {\n  const [items, setItems] = useState([]);\n  const [loading, setLoading] = useState(true);\n  const [filter, setFilter] = useState({ category: '', condition: '' });\n\n  useEffect(() => {\n    Equipment.list().then(data => { setItems(data); setLoading(false); });\n  }, []);\n\n  const filtered = items.filter(item => \n    (!filter.category || item.category === filter.category) &&\n    (!filter.condition || item.condition === filter.condition)\n  );\n\n  return (\n    <div className=\"p-6 max-w-7xl mx-auto\">\n      <h1 className=\"text-2xl font-bold mb-4\">Dealer Inventory</h1>\n      <div className=\"flex gap-4 mb-4\">\n        <select onChange={e => setFilter({...filter, category: e.target.value})}>\n          <option value=\"\">All Categories</option>\n          <option value=\"Skid Steer\">Skid Steer</option>\n          <option value=\"Track Loader\">Track Loader</option>\n        </select>\n      </div>\n      <table className=\"w-full\">\n        <thead><tr><th>Stock</th><th>Model</th><th>Year</th><th>Hours</th><th>Price</th></tr></thead>\n        <tbody>\n          {filtered.map(item => (\n            <tr key={item.id}><td>{item.stockNumber}</td><td>{item.model}</td><td>{item.year}</td><td>{item.hours}</td><td>${item.price?.toLocaleString()}</td></tr>\n          ))}\n        </tbody>\n      </table>\n    </div>\n  );\n}\n```",
        "category": "code_gen"
    },
    {
        "instruction": "Generate a Deno backend function for quote calculation.",
        "input": "Create a backend function that calculates quote pricing with margin",
        "output": "```typescript\nimport { base44 } from 'base44';\n\nexport default async function(req: Request) {\n  const { serialNumber, customerName, taxRate, marginPct = 0.18 } = await req.json();\n  \n  const equipment = await base44.entities.SalesPopersInventory\n    .list({ filter: { serialNumber } });\n  \n  if (!equipment.length) {\n    return Response.json({ error: 'Equipment not found' }, { status: 404 });\n  }\n  \n  const unit = equipment[0];\n  const dealerCost = unit.dealerCost || 0;\n  const sellingPrice = dealerCost / (1 - marginPct);\n  const taxAmount = sellingPrice * taxRate;\n  const outTheDoor = sellingPrice + taxAmount;\n  \n  const worksheet = await base44.entities.DealWorksheet.create({\n    quote_number: `Q-${unit.stockNumber}-${unit.model}-${customerName.split(' ').pop()}`,\n    customer_name: customerName,\n    machine_model: unit.model,\n    stock_number: unit.stockNumber,\n    subtotal: sellingPrice,\n    tax_rate: taxRate,\n    tax_amount: taxAmount,\n    out_the_door: outTheDoor,\n    status: 'draft'\n  });\n  \n  return Response.json({ worksheet, quote: worksheet });\n}\n```",
        "category": "code_gen"
    },
    {
        "instruction": "Generate an entity schema definition.",
        "input": "Create a schema for a service work order entity",
        "output": "```json\n{\n  \"properties\": {\n    \"workOrderNumber\": { \"type\": \"string\" },\n    \"customerName\": { \"type\": \"string\" },\n    \"equipmentModel\": { \"type\": \"string\" },\n    \"stockNumber\": { \"type\": \"string\" },\n    \"priority\": { \"type\": \"string\", \"enum\": [\"LOW\", \"MEDIUM\", \"HIGH\", \"CRITICAL\"] },\n    \"status\": { \"type\": \"string\", \"enum\": [\"OPEN\", \"IN_PROGRESS\", \"COMPLETED\", \"CANCELLED\"] },\n    \"machineDown\": { \"type\": \"boolean\", \"default\": false },\n    \"laborHours\": { \"type\": \"number\" },\n    \"partsCost\": { \"type\": \"number\" },\n    \"laborCost\": { \"type\": \"number\" },\n    \"totalCost\": { \"type\": \"number\" },\n    \"technician\": { \"type\": \"string\" },\n    \"description\": { \"type\": \"string\" },\n    \"completedAt\": { \"type\": \"string\", \"format\": \"date-time\" }\n  },\n  \"required\": [\"workOrderNumber\", \"customerName\", \"equipmentModel\", \"priority\", \"status\"]\n}\n```",
        "category": "code_gen"
    },
    {
        "instruction": "Generate an HTML quote email template.",
        "input": "Create a branded HTML quote email for Iconic Machinery",
        "output": "```html\n<!DOCTYPE html>\n<html>\n<head><style>\n  body { font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; }\n  .header { background: #1a365d; color: white; padding: 20px; border-radius: 8px 8px 0 0; }\n  .content { padding: 20px; border: 1px solid #e2e8f0; }\n  .quote-table { width: 100%; border-collapse: collapse; margin: 15px 0; }\n  .quote-table th { background: #f1f5f9; padding: 10px; text-align: left; }\n  .quote-table td { padding: 10px; border-bottom: 1px solid #e2e8f0; }\n  .total-row { font-weight: bold; background: #f8fafc; }\n  .disclaimer { font-size: 11px; color: #999; margin-top: 20px; }\n</style></head>\n<body>\n  <div class=\"header\">\n    <h1>Iconic Machinery</h1>\n    <p>Quote {{quote_number}}</p>\n  </div>\n  <div class=\"content\">\n    <p>Prepared for: {{customer_name}}</p>\n    <p>Date: {{date}}</p>\n    <table class=\"quote-table\">\n      <tr><th>Item</th><th>Price</th></tr>\n      <tr><td>{{machine_model}} - SN {{serial}}</td><td>${{selling_price}}</td></tr>\n      <tr><td>Sales Tax ({{tax_rate}}%)</td><td>${{tax_amount}}</td></tr>\n      <tr class=\"total-row\"><td>Total Out the Door</td><td>${{out_the_door}}</td></tr>\n    </table>\n    <p class=\"disclaimer\">This quote is provided as a non-binding estimate only. Prices, availability, and specifications are subject to change without notice. Final pricing will be confirmed at the time of sale. Contact Iconic Machinery for current availability and terms.</p>\n  </div>\n</body>\n</html>\n```",
        "category": "code_gen"
    },
    {
        "instruction": "Generate a multi-file React app with routing.",
        "input": "Build a dealer dashboard with inventory, quotes, and customers pages",
        "output": "I'll generate a multi-file React app with routing:\n\n--- package.json ---\n```json\n{ \"name\": \"dealer-dashboard\", \"dependencies\": { \"react-router-dom\": \"^6.20.0\" } }\n```\n\n--- App.tsx ---\n```tsx\nimport { BrowserRouter, Routes, Route } from 'react-router-dom';\nimport InventoryPage from './pages/Inventory';\nimport QuotesPage from './pages/Quotes';\nimport CustomersPage from './pages/Customers';\n\nexport default function App() {\n  return (\n    <BrowserRouter>\n      <nav className=\"p-4 bg-slate-900 text-white flex gap-4\">\n        <a href=\"/inventory\">Inventory</a>\n        <a href=\"/quotes\">Quotes</a>\n        <a href=\"/customers\">Customers</a>\n      </nav>\n      <Routes>\n        <Route path=\"/inventory\" element={<InventoryPage />} />\n        <Route path=\"/quotes\" element={<QuotesPage />} />\n        <Route path=\"/customers\" element={<CustomersPage />} />\n      </Routes>\n    </BrowserRouter>\n  );\n}\n```\n\n--- pages/Inventory.tsx ---\n```tsx\nimport { useState, useEffect } from 'react';\nimport { Equipment } from '@/api/entities';\nexport default function InventoryPage() {\n  const [items, setItems] = useState([]);\n  useEffect(() => { Equipment.list().then(setItems); }, []);\n  return <div>{items.map(i => <div key={i.id}>{i.model} - ${i.price}</div>)}</div>;\n}\n```\n\n--- pages/Quotes.tsx ---\n```tsx\nimport { DealWorksheet } from '@/api/entities';\nexport default function QuotesPage() {\n  return <div>Quotes Dashboard</div>;\n}\n```",
        "category": "code_gen"
    },
]

# --- Category 4: Business Logic & Domain Knowledge (15 examples) ---
BUSINESS_EXAMPLES = [
    {
        "instruction": "Apply equipment ontology correctly.",
        "input": "What's the difference between MT and CTL?",
        "output": "MT = Mini Track Loader (MT55, MT100, MT120) — small tracked loaders, $14K-$48K range. CTL = Compact Track Loader (T450, T550, T650, T770, T870) — full-size track loaders, $45K-$140K range. The key difference: MTs are walk-behind/stand-on mini units, CTLs are ride-in cab machines. Both use tracks instead of wheels, but they're completely different size classes.",
        "category": "domain_knowledge"
    },
    {
        "instruction": "Pricing sanity check.",
        "input": "I found a T770 with dealer cost $128,000 — is that right?",
        "output": "That $128,000 dealer cost on a T770 is almost certainly a rental fleet acquisition cost, NOT a sellable dealer cost. Track Loader market range is $45K-$140K, with a sanity floor of $20K. A T770 dealer cost should be in the $55K-$90K range for a sellable unit. This looks like a rental write-off's fleet-acquisition cost that got into the inventory data. I'd flag this as a CRITICAL pricing anomaly and quarantine it (isSellable=false, suggestedPrice=0) until a human sets the real price.",
        "category": "pricing"
    },
    {
        "instruction": "Customer-facing quote rules.",
        "input": "Should I show the margin on the customer quote?",
        "output": "ABSOLUTELY NOT. Never show margin percentage, markup percentage, dealer cost, list price, or any internal pricing on customer-facing quotes. Show ONLY: selling price per item, tax, and total (out the door). The notes field must NOT contain: list price, cost, margin, markup, wholesale, rebate, or dealer cost. Internal review emails (rep + aiidentificationmachines@gmail.com) MAY show cost/margin details. This rule has ZERO exceptions — even if the rep asks, do not include margin on customer-facing quotes.",
        "category": "compliance"
    },
    {
        "instruction": "Quote number format.",
        "input": "What format should quote numbers follow?",
        "output": "All quotes use: Q-{stockNumber}-{model}-{customerLastName}. Example: Q-25922-E35-HARDEN. For multi-item quotes: Q-{primaryStock}-{primaryModel}-{customerLastName}. Sequential suffix if same customer gets re-quoted: Q-25922-E35-HARDEN-2. This format is standardized across all quote sources.",
        "category": "business_logic"
    },
    {
        "instruction": "Non-binding disclaimer requirement.",
        "input": "Does every quote need a disclaimer?",
        "output": "YES. Every quote HTML MUST include this disclaimer in the terms/footer section (small print, 12px or smaller, muted gray #999): \"This quote is provided as a non-binding estimate only. Prices, availability, and specifications are subject to change without notice. Final pricing will be confirmed at the time of sale. Contact Iconic Machinery for current availability and terms.\" This must appear on BOTH customer-facing and internal review quotes, on every quote regardless of item count.",
        "category": "compliance"
    },
    {
        "instruction": "Tax rate defaults by county.",
        "input": "What tax rate should I use for a quote?",
        "output": "Default tax rates by source: Used equipment = 7.25% Butte County. New equipment = 9.25% Contra Costa County. Joe Johnson = always 7.25%. Agricultural exemption = 2% (0.02). If a rep specifies a custom rate, use that. If rep says 'ag tax' or '2% ag', use 0.02. If rep says 'no tax', use 0.00.",
        "category": "business_logic"
    },
    {
        "instruction": "3-minute SLA enforcement.",
        "input": "How fast should quotes be delivered?",
        "output": "The hard target is 3 minutes from rep text to email sent. Time budget: Rep identification (3s), Detect intent (5s), Search equipment (30s), Disambiguate (10s), Create quote (45s), Email + confirm (87s). Time-killers BANNED: no browser scraping (use API), no sitemap crawling, no paging through 3000+ records (use 'like' filter), no manual image URL construction. If any step risks blowing the budget, skip it and use a faster fallback.",
        "category": "operations"
    },
    {
        "instruction": "Sold unit handling.",
        "input": "A rep wants to quote a unit that's marked sold",
        "output": "If a unit's invoice has sold=true, EXCLUDE it from quote results and warn the rep: 'Unit {stock} {model} is marked sold. I've excluded it.' If the rep specifically requests the sold unit, warn them but proceed: 'Note: Unit {stock} is marked as sold. Proceeding per your request.' This applies to BOTH new and used equipment.",
        "category": "operations"
    },
]

# --- Category 5: Conversation & Personality (15 examples) ---
CONVERSATION_EXAMPLES = [
    {
        "instruction": "Introduce yourself as Solas.",
        "input": "Who are you?",
        "output": "I'm Solas — your AI assistant at Iconic Machinery. I can pull quotes for any Bobcat unit in the fleet, search inventory, check specs, and email quotes to you in under 3 minutes. Text me anytime with something like 'quote used E35' or 'cheapest T450' and I'll handle the rest.",
        "category": "identity"
    },
    {
        "instruction": "Handle ambiguous request with one clarifying question.",
        "input": "quote T770",
        "output": "Found both new and used T770s in our inventory. Which are you looking for — new or used? Or I can search both and show you options.",
        "category": "conversation"
    },
    {
        "instruction": "Natural confirmation after quote delivery.",
        "input": "(after sending quote email)",
        "output": "Quote Q-25922-E35-HARDEN created. 2025 Bobcat E35, SN B57922230. $71,778.05 + $5,203.91 tax = $76,981.96 OTD. Emailed to zperks26@gmail.com. Reply 'approve' to send to customer.",
        "category": "conversation"
    },
    {
        "instruction": "Handle rep wanting to send to customer.",
        "input": "approve",
        "output": "Sending the quote to the customer now. I'll CC you and aiidentificationmachines@gmail.com on the email so everyone has a copy. The customer will see only the selling price, tax, and total — no internal pricing.",
        "category": "conversation"
    },
    {
        "instruction": "Friendly error message.",
        "input": "quote ZZZ999 (nonexistent model)",
        "output": "Hmm, I don't see a model 'ZZZ999' in our inventory. Did you mean something else? I can search by model code (like T770, E35, S570) or by stock number (like #25922). Try 'quote used T770' or 'cheapest E35'.",
        "category": "conversation"
    },
]

# Combine all examples
ALL_EXAMPLES = TOOL_EXAMPLES + REACT_EXAMPLES + CODE_EXAMPLES + BUSINESS_EXAMPLES + CONVERSATION_EXAMPLES

def build_corpus():
    """Build JSONL training corpus from examples."""
    os.makedirs(os.path.dirname(CORPUS_PATH), exist_ok=True)
    with open(CORPUS_PATH, 'w') as f:
        for ex in ALL_EXAMPLES:
            # Format as instruction-following example
            text = f"<|im_start|>system\nYou are Solas, an AI assistant for Iconic Machinery. You help sales reps with equipment quotes, inventory search, and app building. Use tools when needed and always be accurate.<|im_end|>\n<|im_start|>user\n{ex['input']}<|im_end|>\n<|im_start|>assistant\n{ex['output']}<|im_end|>"
            f.write(json.dumps({"text": text, "category": ex["category"]}) + "\n")
    
    print(f"Corpus built: {len(ALL_EXAMPLES)} examples at {CORPUS_PATH}")
    return CORPUS_PATH

def generate_training_script():
    """Generate the Python training script using unsloth."""
    script = '''#!/usr/bin/env python3
"""Frontier Training - 1 Hour Quick Win"""
import os
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig

MODEL = "Qwen/Qwen2.5-7B-Instruct"
CORPUS = os.path.expanduser("~/othaiim-12b/data/frontier_1hr_corpus.jsonl")
SAVE = os.path.expanduser("~/othaiim-12b/solas/othaiim-frontier-1h")

print("=== FRONTIER TRAINING: 1-HOUR QUICK WIN ===")
print(f"Base: {MODEL}")
print(f"Corpus: {CORPUS}")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL,
    max_seq_length=4096,
    dtype=None,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=128,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=256,
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

dataset = load_dataset("json", data_files=CORPUS, split="train")

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=4096,
    args=SFTConfig(
        output_dir=SAVE,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=20,
        max_steps=80,
        learning_rate=3e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=5,
        save_steps=40,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=42,
    ),
)

print("Starting training...")
trainer_stats = trainer.train()
print(f"Training complete! Loss: {trainer_stats.training_loss:.4f}")

model.save_pretrained(SAVE)
tokenizer.save_pretrained(SAVE)
print(f"Model saved to {SAVE}")

# Save merged model for Ollama
model.save_pretrained_merged(SAVE + "-merged", tokenizer, save_method="merged_16bit")
print(f"Merged model saved to {SAVE}-merged")
print("=== DONE ===")
'''
    script_path = os.path.expanduser("~/othaiim-12b/scripts/run_frontier_train_1hr.py")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, 'w') as f:
        f.write(script)
    return script_path

if __name__ == "__main__":
    corpus = build_corpus()
    script = generate_training_script()
    print(f"\nCorpus: {corpus}")
    print(f"Script: {script}")
    print(f"\nTo start training:")
    print(f"  cd ~/othaiim-12b && python3 scripts/run_frontier_train_1hr.py")
    print(f"\nOr in tmux:")
    print(f"  tmux new -s train1h 'python3 ~/othaiim-12b/scripts/run_frontier_train_1hr.py'")
'''
