import json
import os
import urllib.request


class LlmClient:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set")

        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You output only JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")

        parsed = json.loads(body)
        return parsed["choices"][0]["message"]["content"]
