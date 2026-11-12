from pathlib import Path
from fastapi.responses import FileResponse

from fastapi import FastAPI, HTTPException
from ollama import Client, ResponseError



from pydantic import BaseModel, Field

app = FastAPI(title="Linux Learning Tutor")
client = Client(host="http://127.0.0.1:11434")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@app.get("/", response_class=FileResponse)
def home():
    page = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return FileResponse(page)


@app.post("/ask")
def ask_tutor(request: Question):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question.")

    try:
        response = client.chat(
            model="llama3.2",
            messages=[
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
                {"role": "user", "content": question},
            ],
        )
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
