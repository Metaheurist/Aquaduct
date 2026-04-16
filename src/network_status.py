"""
Best-effort internet reachability for UI messaging only.

Does not guarantee Hugging Face or any specific host; only detects typical “no route” / captive / DNS failures.
"""

from __future__ import annotations


def is_internet_likely_reachable(*, timeout_s: float = 3.0) -> bool:
    """
    Return True if a short HTTPS request to a public endpoint succeeds.

    Failure means offline, firewall blocking outbound HTTPS, or captive portal — treat as “no internet” for UX.
    Tries more than one host so one blocked URL does not always imply offline.
    """
    import requests

    probes = (
        ("https://www.microsoft.com/connecttest.txt", True),  # expect tiny body
        ("https://huggingface.co/", False),  # expect HTML 200
    )
    headers = {"User-Agent": "Aquaduct/1.0"}

    for url, want_body in probes:
        try:
            r = requests.get(url, timeout=timeout_s, headers=headers)
            if not r.ok:
                continue
            if want_body and not (r.text or "").strip():
                continue
            return True
        except Exception:
            continue
    return False
