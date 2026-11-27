from fastapi.responses import HTMLResponse
from ui import INDEX_HTML
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
from pydantic import field_validator

import secrets
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
import os
import time
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

load_dotenv()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30000),  # 30 seconds, in milliseconds
)

app = FastAPI(title="API Request Generator")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(api_key_header)):
    if not key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send it in the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    valid_keys = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
    if not any(secrets.compare_digest(key, v) for v in valid_keys):
        raise HTTPException(status_code=403, detail="Invalid API key.")
    return key


class PromptIn(BaseModel):
    prompt: str
    webhook_url: Optional[str] = None

    @field_validator("webhook_url")
    @classmethod
    def must_be_https(cls, v):
        if v and not v.startswith("https://"):
            raise ValueError("webhook_url must start with https://")
        return v


class KeyValue(BaseModel):
    key: str
    value: str


class GeneratedRequest(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: str
    headers: list[KeyValue]
    query_params: list[KeyValue]
    body: Optional[str] = None  # JSON string, or null if no body
    explanation: str


SYSTEM_PROMPT = (
    "You convert natural language descriptions into precise HTTP API requests. "
    "Use real, publicly documented API endpoints when the user names a service. "
    "Never invent secrets: use placeholders like YOUR_API_KEY for credentials. "
    "Keep the explanation to one or two sentences."
)

MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
]

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return INDEX_HTML

@app.get("/health")
def health():
    return {"status": "ok"}

def send_webhook(url: str, data: dict):
    payload = {
        "id": str(uuid.uuid4()),
        "event": "request.generated",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(
        os.getenv("WEBHOOK_SECRET", "").encode(), body, hashlib.sha256
    ).hexdigest()
    try:
        httpx.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Event": "request.generated",
                "X-Webhook-Signature": f"sha256={signature}",
            },
            timeout=10,
        )
    except httpx.HTTPError as e:
        print(f"Webhook delivery failed: {e}")

@app.post("/generate", response_model=GeneratedRequest, dependencies=[Depends(require_api_key)])
def generate(data: PromptIn):
    last_error = None
    for model in MODELS:  # try the main model first, then the fallback
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=data.prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=GeneratedRequest,
                    ),
                )
                result = response.parsed
                print("webhook_url received:", data.webhook_url)
                if data.webhook_url:
                    send_webhook(data.webhook_url, result.model_dump())
                return result
            except errors.ServerError as e:
                # 5xx (e.g. 503 overloaded): short wait, retry once, then next model
                last_error = e
                time.sleep(1)
            except errors.ClientError as e:
                last_error = e
                if e.code in (404, 429):
                    break  # model unavailable or rate limited: go to next model
                raise HTTPException(status_code=502, detail=f"Gemini error: {e}")
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Gemini error: {e}")

    if isinstance(last_error, errors.ClientError) and last_error.code == 429:
        raise HTTPException(
            status_code=429,
            detail="Rate limit reached. Please retry in about a minute.",
            headers={"Retry-After": "60"},
        )
    raise HTTPException(
        status_code=503,
        detail=f"All Gemini models are busy, please retry shortly. ({last_error})",
    )