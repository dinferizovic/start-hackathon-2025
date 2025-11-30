# Negotiation Workflow Backend

FastAPI backend that orchestrates the end-to-end vendor negotiation flow described in the hackathon brief. It integrates with AskLio's public API for vendor conversations and OpenAI for reasoning, extraction, and negotiation strategy.

## Getting Started

1. **Create a virtual environment** (Python 3.11+ recommended):

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials:**

   The app automatically reads
   - `OPENAI_API_KEY` from environment or from `OPENAI_APIKEY.txt` at repo root.
   - `ASKLIO_BASE_URL` / `ASKLIO_TEAM_ID` from environment (defaults come from `APIS_ASKLIO.txt`).

   You can override defaults via environment variables or a `.env` file before starting the server.

4. **Run the development server:**

   ```bash
   uvicorn app.main:app --reload --app-dir backend
   ```

   Visit `http://127.0.0.1:8000/docs` for interactive API docs.

## API

`POST /workflows/negotiate` runs the full 12-step flow (intake → vendor scoring → second-round negotiation → trade-off options).

Example payload:

```json
{
  "intake": {
    "initial_request": "Need 2 espresso machines and 1 grinder for Berlin HQ next month.",
    "budget": 7000,
    "delivery_deadline": "2024-11-01",
    "location": "Berlin, Germany",
    "weights": { "price": 0.4, "quality": 0.25, "delivery": 0.2, "prestige": 0.1, "sustainability": 0.05 },
    "constraints": ["Minimum 2-year warranty", "Require installation"]
  }
}
```

The response contains:
- `intake_summary`: structured requirements plus clarifying questions.
- `shortlisted_vendors`: Top 5 vendors with both negotiation rounds, extracted data, and weighted scores.
- `tradeoff_options`: Four final recommendations (Best Price, Best Quality, Fastest Delivery, Balanced).

You can reuse `backend/example_request.json` and run:

```bash
curl -X POST http://127.0.0.1:8000/workflows/negotiate \
  -H "Content-Type: application/json" \
  --data @backend/example_request.json
```

## Project Structure

```
backend/
  app/
    config.py        # Settings + credential loading
    main.py          # FastAPI entrypoint
    routers/         # Route definitions
    services/        # Business logic + workflow orchestration
    clients/         # Wrappers around OpenAI + AskLio HTTP APIs
    schemas/         # Pydantic models for request/response contracts
    workflows/       # High-level workflow coordinators
```

## Next Steps

- Add persistence/caching for vendor responses or allow resuming in-progress workflows.
- Extend the API to expose intermediate checkpoints (intake-only, first-round results).
- Add automated tests and observability/logging hooks.

## Logging

Every workflow run logs each major step (intake summary, prompts, AskLio replies, extracted offers, scores, trade-off options) through the `negotiation.workflow` logger. Run the server in the foreground to watch the prompts/responses stream by while testing.
