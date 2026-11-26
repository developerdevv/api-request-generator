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


class PromptIn(BaseModel):
    prompt: str


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GeneratedRequest)
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
                return response.parsed
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