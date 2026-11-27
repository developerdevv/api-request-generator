# API Request Generator

Describe an API call in plain English and get back a structured, ready-to-run
HTTP request (method, URL, headers, query params, body) plus cURL, fetch and
Python snippets. Built with FastAPI and the Gemini API.

**Live demo:** https://api-request-generator.vercel.app
**API docs (Swagger):** https://api-request-generator.vercel.app/docs

## Features

- Natural language to structured API request using Gemini structured output
- Automatic fallback to a second Gemini model on 503/429 errors, with retries
- API key authentication (`X-API-Key` header)
- HMAC-SHA256 signed webhooks for delivering results to other applications
- Web UI with copy-ready cURL, fetch and Python snippets
- Interactive API documentation (OpenAPI/Swagger)

## Tech stack

Python, FastAPI, Pydantic, Google Gemini API (`google-genai`), httpx, Vercel

## Run locally

```bash
git clone https://github.com/developerdevv/api-request-generator.git
cd api-request-generator
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (never commit it):

```
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
API_KEYS=rg_key_one,rg_key_two
WEBHOOK_SECRET=long_random_string
```

Generate keys with:
`python -c "import secrets; print('rg_' + secrets.token_urlsafe(32))"`

Start the server: `uvicorn main:app --reload`, then open http://127.0.0.1:8000

## API reference

### Authentication

Send a valid key in the `X-API-Key` header.

| Status | Meaning |
|--------|---------|
| 401 | Header missing |
| 403 | Key invalid |

### POST /generate

Request body:

```json
{
  "prompt": "Create a new GitHub issue titled 'Login bug' in repo devv/demo-app",
  "webhook_url": "https://example.com/hook"
}
```

`webhook_url` is optional and must start with `https://`.

Response `200`:

```json
{
  "method": "POST",
  "url": "https://api.github.com/repos/devv/demo-app/issues",
  "headers": [{"key": "Authorization", "value": "Bearer YOUR_API_KEY"}],
  "query_params": [],
  "body": "{\"title\":\"Login bug\"}",
  "explanation": "Creates a new issue in the repository."
}
```

| Status | Meaning |
|--------|---------|
| 200 | Request generated |
| 401 / 403 | Missing or invalid API key |
| 422 | Invalid request body |
| 429 | Gemini rate limit reached (see `Retry-After` header) |
| 502 | Upstream Gemini error |
| 503 | All Gemini models busy, retry shortly |

Example:

```bash
curl -X POST https://YOUR-APP.vercel.app/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"prompt": "Get the current weather for Bengaluru from OpenWeatherMap"}'
```

### GET /health

Returns `{"status": "ok"}`. No authentication required.

## Webhooks

If `webhook_url` is provided, the app sends a `POST` to that URL after
generating the request.

Headers:

- `Content-Type: application/json`
- `X-Webhook-Event: request.generated`
- `X-Webhook-Signature: sha256=<hex digest>`

Payload:

```json
{
  "id": "uuid",
  "event": "request.generated",
  "created_at": "2026-11-27T10:00:00+00:00",
  "data": { "method": "POST", "url": "...", "headers": [], "query_params": [], "body": "...", "explanation": "..." }
}
```

The signature is `HMAC-SHA256(WEBHOOK_SECRET, raw request body)`. Receivers
should verify it:

```python
import hmac, hashlib

def verify(raw_body: bytes, header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
```

Webhook delivery failures never affect the `/generate` response.

## Security

- Secrets are loaded from environment variables, never hardcoded
- API keys are compared in constant time
- Webhook URLs must use HTTPS
- Generated requests use placeholders (e.g. `YOUR_API_KEY`), never real secrets