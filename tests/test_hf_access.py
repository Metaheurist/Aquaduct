from src.hf_access import humanize_hf_hub_error


def test_humanize_gated_repo_error():
    class E(Exception):
        pass

    msg = humanize_hf_hub_error(
        E("401 Client Error: you are trying to access a gated repo for meta-llama/Meta-Llama-3.1-8B-Instruct")
    )
    assert msg is not None
    assert "gated" in msg.lower() or "401" in msg
    assert "huggingface" in msg.lower()
