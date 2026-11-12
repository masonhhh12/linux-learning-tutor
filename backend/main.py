import json
import logging
from pathlib import Path
from typing import Literal
from fastapi.responses import FileResponse, StreamingResponse

from fastapi import FastAPI, HTTPException
from ollama import Client, ResponseError



from pydantic import BaseModel, Field

app = FastAPI(title="Linux Learning Tutor")
client = Client(host="http://127.0.0.1:11434")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


@app.get("/", response_class=FileResponse)
def home():
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


@app.post("/ask")
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


@app.post("/ask/stream")
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
            if stream is not None:
                stream.close()

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
