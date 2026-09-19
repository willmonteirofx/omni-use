"""HTTP sidecar the shell and its floating input talk to (127.0.0.1:8766).

GET  /health          -> {"ok": true, "vision": "loading" | "ready" | "<error>"}
GET  /status          -> the current run's status (or {"state": "idle"})
GET  /debug           -> latest OmniParser boxes + chosen target (debug overlay)
POST /run {"task"}    -> starts a task (one at a time)
POST /pause {"reason"}   the shell's mouse guard calls it when the user takes the mouse
POST /resume          -> continues a paused run / approves a held action
POST /stop            -> ends the run
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import vision
from core import Run
from llm_client import LLMClient

llm = LLMClient()
run = None
vision_state = "loading"


def _warm_up():
    """Loads OmniParser at startup so the first task doesn't wait for it."""
    global vision_state
    try:
        vision.load()
        vision_state = "ready"
    except Exception as e:
        vision_state = f"erro ao carregar o OmniParser: {e}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._reply(204, {})

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"ok": True, "vision": vision_state})
        elif self.path == "/debug":
            self._reply(200, {**run.debug_info, "seq": run.debug_seq} if run else {})
        elif self.path == "/status":
            self._reply(200, run.status() if run else {"state": "idle"})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        global run
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/run":
            task = (body.get("task") or "").strip()
            if not task:
                return self._reply(400, {"error": "tarefa vazia"})
            if run and run.state in ("running", "paused", "confirm"):
                return self._reply(409, {"error": "já existe uma tarefa em andamento"})
            run = Run(task, llm)
            return self._reply(200, run.status())
        if not run:
            return self._reply(409, {"error": "nenhuma tarefa"})
        if self.path == "/pause":
            run.pause(body.get("reason") or "user")
        elif self.path == "/resume":
            run.resume()
        elif self.path == "/stop":
            run.stop()
        else:
            return self._reply(404, {"error": "not found"})
        self._reply(200, run.status())


if __name__ == "__main__":
    threading.Thread(target=_warm_up, daemon=True).start()
    ThreadingHTTPServer((config.SERVER_HOST, config.SERVER_PORT), Handler).serve_forever()
