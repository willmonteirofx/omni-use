import base64
import io
import json
import math

import requests

import config

# Qwen3.5 is a "thinking" model: left on, it writes a reasoning block before
# every tool call, which measured ~2x slower per agent step (1.4-2.4 s vs
# ~0.7 s) for no gain on these short, observation-driven decisions.
NO_THINKING = {"enable_thinking": False}


class LLMClient:
    """Thin client for a local llama.cpp server (OpenAI-compatible /v1 API).
    Blocking; the async agent calls it through asyncio.to_thread so several
    agents can wait on the (multi-slot) server at the same time."""

    def __init__(self, base_url=None):
        self.base_url = base_url or config.LLM_BASE_URL

    def vision(self):
        """Whether llama-server was started with a vision projector (--mmproj).
        Asked every time: the model can be switched in the settings."""
        try:
            props = requests.get(f"{self.base_url}/props", timeout=5).json()
            return bool(props.get("modalities", {}).get("vision"))
        except Exception:
            return False

    def user_content(self, text, image=None):
        """A user message's content: text, plus the image (PIL) when the
        model can see."""
        if image is None or not self.vision():
            return text
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=85)
        url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": text}]

    def _post(self, body):
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions", json=body, timeout=config.LLM_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def chat(self, messages, tools=None, max_tokens=768, temperature=0.2, json_mode=False, thinking=False):
        """Returns (message, prompt_tokens). With thinking, Qwen reasons first
        (message["reasoning_content"]) and then answers in message["content"]."""
        body = {
            "model": "local",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": thinking},
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = self._post(body)
        return data["choices"][0]["message"], data.get("usage", {}).get("prompt_tokens", 0)

    def n_ctx(self):
        """Context size of one server slot (what a single agent can use)."""
        try:
            props = requests.get(f"{self.base_url}/props", timeout=5).json()
            return props["default_generation_settings"]["n_ctx"]
        except Exception:
            return 0

    def decide(self, question, options, state=None, image=None):
        """Decision-native semantic `if` (the OpenJev / SemIf pattern): one
        forward pass over state + question + typed options, reading each
        option's probability as the next token. No answer is generated.

        `options` is a list of ids or (id, description) pairs. Returns
        {id: probability}, or {} when the model put no option among its top
        tokens - callers must treat that as "undecided", never as a yes.
        """
        options = [o if isinstance(o, tuple) else (o, "") for o in options]
        listing = "\n".join(f"- {oid}: {desc}" if desc else f"- {oid}" for oid, desc in options)
        if state is not None and not isinstance(state, str):
            state = json.dumps(state, ensure_ascii=False)
        user = (f"State:\n{state}\n\n" if state else "") + f"Question: {question}\n\nOptions:\n{listing}"
        body = {
            "model": "local",
            "messages": [
                {"role": "system", "content": "Reply with exactly one option id from the list and nothing else."},
                {"role": "user", "content": self.user_content(user, image)},
            ],
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": 20,
            "chat_template_kwargs": NO_THINKING,
        }
        data = self._post(body)["choices"][0]
        top = (data.get("logprobs") or {}).get("content", [{}])[0].get("top_logprobs", [])

        scores = {}
        for entry in top:
            token = entry["token"].strip().lower()
            if not token:
                continue
            for oid, _ in options:
                # The first token of an id may be only a prefix of it.
                if oid.lower().startswith(token) or token == oid.lower():
                    scores[oid] = max(scores.get(oid, -math.inf), entry["logprob"])
        if not scores:
            return {}
        total = sum(math.exp(v) for v in scores.values())
        return {oid: math.exp(scores[oid]) / total if oid in scores else 0.0 for oid, _ in options}
