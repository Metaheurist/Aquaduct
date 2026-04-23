from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.platform.replicate_client import ReplicateClient, ReplicateRequestError


def test_run_prediction_success():
    post_resp = MagicMock()
    post_resp.status_code = 201
    post_resp.json.return_value = {"urls": {"get": "https://api.replicate.com/v1/predictions/p1"}}

    poll1 = MagicMock()
    poll1.status_code = 200
    poll1.json.return_value = {"status": "processing"}

    poll2 = MagicMock()
    poll2.status_code = 200
    poll2.json.return_value = {"status": "succeeded", "output": "https://cdn.example.com/out.png"}

    with patch("src.platform.replicate_client.requests.post", return_value=post_resp) as post:
        with patch("src.platform.replicate_client.requests.get", side_effect=[poll1, poll2]) as get:
            c = ReplicateClient(api_token="r8_test", poll_interval_s=0.01)
            out = c.run_prediction(version="abc123ver", input_payload={"prompt": "hi"})
    assert out == "https://cdn.example.com/out.png"
    post.assert_called_once()
    assert get.call_count == 2


def test_run_prediction_http_error_on_create():
    post_resp = MagicMock()
    post_resp.status_code = 401
    post_resp.text = "unauthorized"
    with patch("src.platform.replicate_client.requests.post", return_value=post_resp):
        c = ReplicateClient(api_token="bad")
        with pytest.raises(ReplicateRequestError) as ei:
            c.run_prediction(version="v", input_payload={})
        assert ei.value.status_code == 401


def test_run_prediction_failed_status():
    post_resp = MagicMock()
    post_resp.status_code = 201
    post_resp.json.return_value = {"urls": {"get": "https://api.replicate.com/v1/predictions/p2"}}

    poll = MagicMock()
    poll.status_code = 200
    poll.json.return_value = {"status": "failed", "error": "OOM"}

    with patch("src.platform.replicate_client.requests.post", return_value=post_resp):
        with patch("src.platform.replicate_client.requests.get", return_value=poll):
            c = ReplicateClient(api_token="r8", poll_interval_s=0.01)
            with pytest.raises(ReplicateRequestError, match="OOM"):
                c.run_prediction(version="v", input_payload={})
