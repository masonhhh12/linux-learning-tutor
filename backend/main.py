from contextlib import asynccontextmanager
import auth
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
import os
from ollama import Client, ResponseError
from pydantic import BaseModel, Field

@asynccontextmanager
async def lifespan(app):
    auth.init_db()
    yield


app = FastAPI(title="Linux Learning Tutor", lifespan=lifespan)
app.include_router(auth.router)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=os.environ.get("TUTOR_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(","),
)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo submitted credentials in validation responses.
    return JSONResponse({"detail": "Invalid request. Check field lengths and formats."}, status_code=422)



@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Bound request bodies before JSON parsing, including chunked requests.
    if request.method == "POST":
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 256000:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Request too large."}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    )
    if request.url.path == "/docs":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
    if auth.SECURE_COOKIES:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

client = Client(host="http://127.0.0.1:11434")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


@app.get("/", response_class=FileResponse)
def home(request: Request):
    if not auth.get_session(request):
        return RedirectResponse("/login", status_code=303)
    page = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return FileResponse(page)


def tutor_messages(request: Question):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question.")
    return [
        {
            "role": "system",
            "content": (
                "You are a patient Linux tutor for beginners. "
                "Explain commands clearly, one step at a time. "
                "Give short examples. Warn before commands that "
                "delete files or change system settings. "
                "Never claim you executed commands."
            ),
        },
        *[message.model_dump() for message in request.history],
        {"role": "user", "content": question},
    ]


@app.post("/ask", dependencies=[Depends(auth.require_session)])
def ask_tutor(request: Question):
    messages = tutor_messages(request)
    try:
        response = client.chat(model="llama3.2", messages=messages)
        return {"answer": response.message.content}
    except ResponseError as exc:
        raise HTTPException(
            status_code=502,
            detail="Ollama could not answer. Check that llama3.2 is installed.",
        ) from exc
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to the Ollama service.",
        ) from exc


@app.post("/ask/stream", dependencies=[Depends(auth.require_session)])
def stream_tutor(request: Question):
    messages = tutor_messages(request)

    def generate():
        stream = None
        try:
            stream = client.chat(
                model="llama3.2", messages=messages, stream=True
            )
            for chunk in stream:
                if chunk.message.content:
                    yield json.dumps({"token": chunk.message.content}) + "\n"
                if chunk.done:
                    yield json.dumps({"done": True}) + "\n"
                    return
            yield json.dumps({"error": "The response ended early. Please try again."}) + "\n"
        except ConnectionError:
            yield json.dumps({"error": "Cannot connect to the Ollama service."}) + "\n"
        except ResponseError:
            yield json.dumps({"error": "Ollama could not answer. Check that llama3.2 is installed."}) + "\n"
        except Exception:
            logging.exception("Tutor stream failed")
            yield json.dumps({"error": "The response was interrupted. Please try again."}) + "\n"
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/login", response_class=FileResponse)
def login_page():
    return FileResponse(Path(__file__).resolve().parent.parent / "frontend" / "login.html")


@app.get("/assets/{name}")
def frontend_asset(name: str):
    if name not in {"app.js", "app.css", "login.js", "login.css"}:
        raise HTTPException(404)
    return FileResponse(Path(__file__).resolve().parent.parent / "frontend" / name)
