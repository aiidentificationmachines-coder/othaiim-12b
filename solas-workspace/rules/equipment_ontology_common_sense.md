# Equipment Ontology & Common-Sense Reasoning (Aug 11-12 2026)

This is the permanent "brain" doctrine for how Solas (and any app built on Solas's
inventory/quote engines, including IM Sales Popers) must understand equipment
categories and sanity-check pricing. Apply these rules in every quote engine,
search function, and pricing audit, on Solas AND when instructing app builders.

## 1. Category / Abbreviation Comprehension

Never rely on raw fuzzy string matching alone for category-level queries
("how many skidsteers", "cheapest MT", "list all telehandlers"). Resolve the
category first, using TWO independent signals combined:

**A. Free-text category aliases** (user-facing synonyms):
- Skid Steer: "skidsteer", "skid steer", "skid-steer", "ssl"
- Mini Track Loader: "mini track loader", "mtl", "MT"
- Track Loader: "track loader", "compact track loader", "ctl", "CTL"
- Excavator: "excavator", "mini excavator", "compact excavator", "electric excavator"
- Telehandler: "telehandler", "forklift", "lift truck"
- Compact Tractor: "compact tractor", "tractor"
- Utility Vehicle: "utility vehicle", "utv", "side by side", "sxs"
- Backhoe Loader: "backhoe", "backhoe loader"
- Wheel Loader: "wheel loader"
- Compressor: "compressor"
- Attachment: "attachment", "implement"

**B. Model-code prefix ontology** (Bobcat naming convention — used as an
independent cross-check so bad/missing category data in inventory records
doesn't break category search):
- `MT` + digits → Mini Track Loader (MT55, MT100, MT120)
- `S` + 2-3 digits → Skid Steer (S70, S86, S185, S250, S450, S510, S570, S590, S650, S740, S770)
- `T` + 3 digits → Track Loader (T450, T550, T595, T650, T740, T770, T870)
- `E` + 1-3 digits (optional `e` suffix for electric) → Excavator (E10e, E17, E19e, E26, E32, E35, E42, E45, E50, E60, E85, E145)
- `CT` + digits → Compact Tractor (CT2025, CT4558HST, CT5558EHST)
- `UV` + digits → Utility Vehicle (UV34, UV34G, UV34XL)
- `TL` + digits → Telehandler (TL519, TL619, TL723) — real telehandlers only
- `B` + 3 digits → Backhoe Loader (B760)
- `L` + 2-3 digits → Wheel Loader (L28, L285)
- `FL` + digit → **Attachment** (pallet fork carriages, $800-$8,000) — NOT
  telehandlers, despite superficially similar naming to `TL`. This was a real
  bug: FL4/FL6/FL7/FL8/FL9/FL10 were mislabeled "Telehandler" in
  EquipmentOntology when their actual dealer cost clusters $1.7K-$5.8K
  (fork attachments), while TL519/TL723 (real telehandlers) run $15K-$115K.

When a category alias is detected and no specific model code matches, filter
inventory by category using BOTH the record's own category/modelCategory field
(if it contains the resolved category name) OR the model-prefix rule applied to
its searchableModel — matching on either is enough (OR logic maximizes recall
against inconsistent category data).

Implemented in `processQuoteRequest` (V15+) on Solas via `resolveCategoryAlias()`,
`MODEL_PREFIX_RULES`, and `inCategory()`. Any app (e.g. IM Sales Popers) that
mirrors Solas's txt-to-quote features must either proxy through this Solas
function or implement the identical ontology locally — do not let a native
app's own search logic diverge without this comprehension layer.

## 2. Pricing Common-Sense Reasoning (Market-Value Sanity Net)

**The core principle:** EquipmentOntology.minPrice/maxPrice is the independent
market-value reference and must NEVER be derived from SalesPopersInventory
itself. Deriving it from inventory is circular — bad data (e.g. a rental
write-off's fleet-acquisition cost) would poison the very reference meant to
catch that bad data. Always source minPrice/maxPrice from either:
1. Parsed `pricingNotes` text containing real market research (e.g.
   "Price range: $58,000-$75,000"), when the parsed low value clears the
   category's sanity floor, OR
2. A category fallback band (real-world 2025-2026 US market ranges):

| Category | Range | Floor (below = corrupted) |
|---|---|---|
| Mini Excavator | $28K-$48K | $12K |
| Electric Mini Excavator | $30K-$55K | $15K |
| Compact/Regular Excavator | $45K-$100K | $20K |
| Large Excavator | $150K-$320K | $80K |
| Skid Steer | $30K-$95K | $15K |
| Skid Steer (R2 Series) | $45K-$105K | $20K |
| Track Loader / CTL | $45K-$140K | $20K |
| CTL (R2 Series) | $55K-$150K | $25K |
| Mini Track Loader | $14K-$48K | $6K |
| Telehandler | $55K-$165K | $25K |
| Compact Tractor | $9K-$55K | $4K |
| Backhoe Loader | $55K-$135K | $25K |
| Wheel Loader | $90K-$260K | $40K |
| Utility Vehicle | $10K-$36K | $4K |
| Compressor | $1.2K-$16K | $400 |
| Part | $20-$6K | $3 |
| Attachment | $100-$40K | $20 |
| Other (misc, no clean category) | $500-$80K | $100 |

**Category resolution for banding:** prefer whichever of `category` /
`modelCategory` is specific (not "Other"/blank) — inventory data is
inconsistent about which field holds the real classification.

**Audit rule (`commonSensePricingAudit` on Solas):** for every inventory
record matched to an ontology entry, compute `lowFloor = minPrice * 0.35`
(allows deep used-equipment discount) and `highCeiling = maxPrice * 1.35`
(allows premium trims). Flag as:
- **CRITICAL**: sellable item's `suggestedPrice` is below `lowFloor`, or
  `dealerCost` is below 15% of `minPrice` — these are the "$1,064 excavator"
  class of catastrophic errors. Auto-quarantine (`isSellable=false`,
  `suggestedPrice=0`) any currently-sellable CRITICAL item immediately —
  never let it be quoted before a human sets a real price.
- **HIGH**: `dealerCost` below `lowFloor` but item already correctly
  unsellable (informational — confirms correct exclusion), or `suggestedPrice`
  above `highCeiling` (possible premium trim, needs human review, not an
  auto-block).

Write every flag to `PricingAnomalyFlag` regardless of severity, so there's a
durable audit trail. Never silently "fix" a price — flag it and let a human
(Marcos) confirm, consistent with the standing "NEVER GUESS PRICES" rule.

## 3. Operational Notes
- `rebuildOntologyPriceBands` and `commonSensePricingAudit` are both
  idempotent — safe to rerun anytime inventory or ontology data changes.
- Run `rebuildOntologyPriceBands` first whenever new EquipmentOntology
  records are added, before running the audit.
- This doctrine applies to BOTH Solas's own engine and any mirrored logic in
  IM Sales Popers or future dealer apps — the category/pricing comprehension
  must be identical everywhere quotes are generated.
