# Othaiim-12B

AI-native dealer operating system built on NVIDIA DGX Spark (GB10 Blackwell, 130.7GB VRAM).

## Overview

Othaiim-12B is the local, offline-capable deployment of the Iconic Machinery AI platform. It runs entirely on the DGX Spark — no cloud dependencies required.

## Architecture

- **Local Base44 API** (port 8890) — Entity CRUD, schemas, aggregation, workflows
- **Elite App Builder** (port 8891) — Natural-language app generation with Qwen2.5:7B
- **Othaiim Agent** (port 8878) — 13-tool ReAct agent with multi-model routing
- **File/Page Server** (port 8882) — Serves generated HTML apps
- **SMS Bridge** (port 8879) — Twilio relay for rep text messages
- **Telegram Bot** (port 8880) — Telegram integration
- **Terminal Server** (port 8888) — Remote command execution via tunnel

## Patent

USPTO 1135-11714-1 — AIIM-governed Dealer OS

## Owner

Marcos Rivas — Othaiim LLC / Iconic Machinery
aiidentificationmachines@gmail.com

## Branches

- `main` — Solas workspace (rules, skills, architecture docs, platform docs)
- `dgx-spark` — Full DGX local repo (scripts, training data, builder, models config)

## License

Proprietary — Othaiim LLC. All rights reserved.
