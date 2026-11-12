# 90-second portfolio demo

## Before recording
- Start Ollama and run ./start.sh from the repository root.
- Open http://localhost:8000, create a demo account, and close unrelated tabs.
- Show registration and sign-in without revealing real passwords.
- Use a browser profile where you are comfortable displaying lesson progress.
- Ask a short question once to warm up the model.
- Do not display personal files, credentials, or terminal history.

## Recording script
**0–15 seconds — Overview**
“This is Linux Learning Tutor, a local learning application built with
FastAPI, JavaScript, and Ollama. It combines structured practice with AI help.”

**15–40 seconds — Learning**
Open navigation. Answer its quiz incorrectly, then choose cd ..
Show immediate feedback and the completion indicator. Refresh to show persistence.

**40–70 seconds — Tutor**
Ask “What does pwd do? Answer briefly.”
Show the answer arriving progressively.
Follow with “Show a safe example.”
Explain that the browser sends recent exchanges for context.

**70–90 seconds — Engineering**
Click New chat. Open API documentation at /docs.
Show the test command and summarize the 31 automated backend tests.
End on the main interface.

## Interview talking points
- FastAPI validates question length and allowed history roles.
- Newline-delimited JSON carries tokens, completion, and failure events.
- Only complete successful responses enter chat memory.
- Browser local storage holds lesson progress; chat is in memory.
- Tests mock the model for repeatable checks without downloading model weights.
- CPU inference latency and lack of authentication are known prototype limits.
- AI generated advice is separate from quizzes, which use fixed answers.

## Resume wording
Built a Linux learning application using Python, FastAPI, JavaScript, and
Ollama, featuring streamed AI tutoring, conversational context, six
interactive lessons, persistent quiz progress, and 31 automated API tests.

Only describe features you can demonstrate. Publish a real recording before
adding a demo link to the README.
