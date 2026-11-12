# Linux Learning Tutor

A local Linux learning app built with FastAPI, HTML/CSS/JavaScript, and Ollama
running llama3.2. No frontend build step or API key is required.

## Features
- Six guided lessons: navigation, files, reading text, search, permissions, pipes.
- Practice quizzes with immediate feedback.
- Completion progress saved in browser local storage when available.
- Streamed AI answers and follow-up questions using the last six exchanges.
- New chat button and interactive API documentation at /docs.

## Setup (Ubuntu / WSL)
Install Python 3, its venv package, and Ollama from https://ollama.com.
Clone this repository and run:

~~~bash
cd linux-learning-tutor
python3 -m venv backend/venv
source backend/venv/bin/activate
python -m pip install -r backend/requirements.txt
ollama pull llama3.2
~~~

Ollama must be running. If installed as a systemd service, use:

~~~bash
sudo systemctl start ollama
~~~

Otherwise run ollama serve in a separate terminal.

## Run
~~~bash
chmod +x start.sh
./start.sh
~~~

Keep the terminal open. Visit http://localhost:8000.
Press Ctrl+C to stop the web app. Ollama runs separately.

## Demo
1. Answer the navigation quiz with cd ..
2. Open another lesson and observe updated progress.
3. Refresh to confirm progress persists.
4. Click Ask tutor about this lesson, then Ask tutor.
5. Ask a follow-up question.
6. Click New chat to clear chat memory.

## API
- GET / serves the learning interface.
- POST /ask returns a JSON answer.
- POST /ask/stream returns newline-delimited JSON token events, ending with
  a done event; failures use an error event.
- GET /docs provides interactive API documentation.

~~~json
{"question": "What does pwd do?", "history": []}
~~~

History accepts user and assistant messages only, up to 12 messages.
Questions are limited to 4,000 characters.

## Troubleshooting
- Page cannot be reached: run ./start.sh and keep its terminal open.
- Port 8000 in use: use the existing app or stop it with Ctrl+C first.
- Ollama unavailable: run ollama list and check its service.
- Model missing: run ollama pull llama3.2.
- Slow first answer: model loading and CPU inference take time.
  Streaming displays text as it is generated.

## Scope
This local learning prototype does not execute commands. AI answers can be
inaccurate. Chat clears on refresh; progress is local to the browser.
There is no login or hosted deployment. The development server listens on
all interfaces for WSL connectivity and has no authentication; use it on
a trusted local machine.
