# Nadid AEE Backend

FastAPI service for the Arabic Editorial Engine.

## Run locally

From `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs:

```
http://localhost:8000/docs
```

## Test

```bash
PYTHONPATH=. pytest -q
```

## v0.1 endpoints

- `GET /health`
- `POST /v1/analyze/docx`
- `POST /v1/validate-patch`
