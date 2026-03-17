---
trigger: always_on
---

# Rule: API & Contract Synchronization

## Context
Trigger this rule whenever the FastAPI backend (`fast_trade/services/api.py`) is modified.

## Requirement
- **Synchronization**: Any change to Pydantic models (requests/responses) or API endpoint logic MUST be reflected in the frontend contract at [`/mnt/projects/News-Dashboard/src/app/types/api-contract.ts`](file:///mnt/projects/News-Dashboard/src/app/types/api-contract.ts).
- **Scope**:
  - `BacktestRequest` / `BacktestResult` (Sync/Async)
  - `LeaderboardEntry` 
  - `Preset` / `PresetRequest`
  - `OptimizeRequest` / `TaskStatus`
- **Validation**:
  - Field names must match exactly.
  - Types must be consistent between Python and TypeScript.
  - Optionality (NULL values) must be handled in both places.
