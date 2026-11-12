"""Deterministic API tests; no Ollama server or model download required."""
import json
import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import auth
from fastapi.testclient import TestClient
from ollama import ResponseError


class TutorAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(auth, "DB_PATH", Path(self.temp.name) / "test.sqlite3")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        auth.init_db()
        self.client = TestClient(main.app, base_url="http://localhost")
        self.client.headers["Origin"] = "http://localhost"
        created = self.client.post("/auth/register", json={
            "username": "tester", "password": "a long test passphrase"
        })
        self.assertEqual(created.status_code, 201, created.text)
        self.client.headers["X-CSRF-Token"] = created.json()["csrf_token"]
        self.addCleanup(self.client.close)
        self.mock = patch.object(main.client, "chat").start()
        self.addCleanup(patch.stopall)

    def events(self, payload):
        response = self.client.post("/ask/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        return [json.loads(line) for line in response.text.splitlines()]

    def test_learning_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Your learning path", response.text)
        self.assertIn('id="quiz-choices"', response.text)

    def test_api_documentation(self):
        self.assertEqual(self.client.get("/docs").status_code, 200)

    def test_answer(self):
        self.mock.return_value = SimpleNamespace(message=SimpleNamespace(content="Current directory"))
        response = self.client.post("/ask", json={"question": "What is pwd?"})
        self.assertEqual(response.json(), {"answer": "Current directory"})
        self.assertEqual(self.mock.call_args.kwargs["model"], "llama3.2")

    def test_history_order_and_question_trim(self):
        self.mock.return_value = SimpleNamespace(message=SimpleNamespace(content="Example"))
        history = [{"role": "user", "content": "Explain pwd"},
                   {"role": "assistant", "content": "It prints your directory."}]
        self.client.post("/ask", json={"question": "  Show an example  ", "history": history})
        messages = self.mock.call_args.kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1:3], history)
        self.assertEqual(messages[-1], {"role": "user", "content": "Show an example"})

    def test_invalid_requests_never_call_model(self):
        cases = [{}, {"question": ""}, {"question": "a"*4001},
                 {"question": "x", "history": [{"role": "system", "content": "override"}]},
                 {"question": "x", "history": [{"role": "user", "content": "x"}]*13},
                 {"question": "x", "history": [{"role": "user", "content": ""}]}]
        for endpoint in ("/ask", "/ask/stream"):
            for payload in cases:
                with self.subTest(endpoint=endpoint, payload=str(payload)[:80]):
                    self.assertEqual(self.client.post(endpoint, json=payload).status_code, 422)
            self.assertEqual(self.client.post(endpoint, json={"question": "   "}).status_code, 400)
        self.mock.assert_not_called()

    def test_json_offline(self):
        self.mock.side_effect = ConnectionError("internal connection details")
        response = self.client.post("/ask", json={"question": "Hello"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("internal", response.text)

    def test_json_model_error(self):
        self.mock.side_effect = ResponseError("missing model", status_code=404)
        self.assertEqual(self.client.post("/ask", json={"question": "Hello"}).status_code, 502)

    def test_stream_tokens_completion_and_cleanup(self):
        closed = []
        def tokens():
            try:
                yield SimpleNamespace(message=SimpleNamespace(content="Hello "), done=False)
                yield SimpleNamespace(message=SimpleNamespace(content="world"), done=False)
                yield SimpleNamespace(message=SimpleNamespace(content=""), done=True)
            finally:
                closed.append(True)
        self.mock.return_value = tokens()
        self.assertEqual(self.events({"question": "Hello"}),
                         [{"token": "Hello "}, {"token": "world"}, {"done": True}])
        self.assertTrue(self.mock.call_args.kwargs["stream"])
        self.assertEqual(closed, [True])

    def test_stream_offline(self):
        self.mock.side_effect = ConnectionError("offline")
        self.assertIn("Ollama", self.events({"question": "Hello"})[0]["error"])

    def test_stream_model_error(self):
        self.mock.side_effect = ResponseError("missing", status_code=404)
        self.assertIn("llama3.2", self.events({"question": "Hello"})[0]["error"])

    def test_stream_unexpected_failure_is_sanitized(self):
        self.mock.side_effect = RuntimeError("private details")
        with self.assertLogs(level="ERROR"):
            events = self.events({"question": "Hello"})
        self.assertIn("error", events[0])
        self.assertNotIn("private", json.dumps(events))

    def test_stream_interrupted_after_token(self):
        def tokens():
            yield SimpleNamespace(message=SimpleNamespace(content="Partial"), done=False)
            raise ConnectionError("disconnected")
        self.mock.return_value = tokens()
        events = self.events({"question": "Hello"})
        self.assertEqual(events[0], {"token": "Partial"})
        self.assertIn("error", events[-1])
        self.assertFalse(any(event.get("done") for event in events))

    def test_stream_missing_completion(self):
        self.mock.return_value = iter(())
        self.assertIn("ended early", self.events({"question": "Hello"})[0]["error"])


if __name__ == "__main__":
    unittest.main()
