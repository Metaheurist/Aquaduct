from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


class ReplicateRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _map_err(status: int, body: str) -> str:
    if status in (401, 403):
        return "Replicate rejected the request — check REPLICATE_API_TOKEN."
    if status == 429:
        return "Replicate rate limited — retry later."
    return f"Replicate HTTP {status}: {(body or '')[:400]}"


@dataclass
class ReplicateClient:
    api_token: str
    timeout: float = 120.0
    poll_interval_s: float = 1.5

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.api_token.strip()}",
            "Content-Type": "application/json",
        }

    def run_prediction(self, *, version: str, input_payload: dict[str, Any]) -> Any:
        """Create a prediction and poll until terminal status. Returns parsed output field."""
        url = "https://api.replicate.com/v1/predictions"
        body = {"version": version.strip(), "input": input_payload}
        try:
            r = requests.post(url, headers=self._headers(), json=body, timeout=self.timeout)
        except requests.RequestException as e:
            raise ReplicateRequestError(f"Replicate network error: {e}") from e
        if r.status_code >= 400:
            raise ReplicateRequestError(_map_err(r.status_code, r.text), status_code=r.status_code)
        pred = r.json()
        pred_url = str(pred.get("urls", {}).get("get") or pred.get("url") or "")
        if not pred_url:
            raise ReplicateRequestError("Replicate did not return a prediction URL.")
        deadline = time.time() + 25 * 60
        while time.time() < deadline:
            try:
                pr = requests.get(pred_url, headers=self._headers(), timeout=self.timeout)
            except requests.RequestException as e:
                raise ReplicateRequestError(f"Replicate poll failed: {e}") from e
            if pr.status_code >= 400:
                raise ReplicateRequestError(_map_err(pr.status_code, pr.text), status_code=pr.status_code)
            j = pr.json()
            st = str(j.get("status") or "")
            if st in ("succeeded", "failed", "canceled"):
                if st != "succeeded":
                    raise ReplicateRequestError(str(j.get("error") or f"Prediction {st}."))
                return j.get("output")
            time.sleep(self.poll_interval_s)
        raise ReplicateRequestError("Replicate prediction timed out while polling.")
