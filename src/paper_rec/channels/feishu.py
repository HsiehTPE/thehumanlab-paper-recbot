from __future__ import annotations

import json
import urllib.request


class FeishuChannel:
    def __init__(self, webhook_url: str, timeout: int = 30) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, content: str) -> None:
        payload = json.dumps(
            {"msg_type": "text", "content": {"text": content}}, ensure_ascii=False
        ).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("code", result.get("StatusCode", 0)) != 0:
            raise RuntimeError(f"Feishu rejected the message: {result}")

