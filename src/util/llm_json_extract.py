"""Best-effort extraction of a JSON object from LLM text (fences, prose, partial parses)."""

from __future__ import annotations

import json
import re
from typing import Any


def repair_llm_json_text_escapes(s: str) -> str:
    """Fix invalid ``\\'`` sequences LLMs often emit inside JSON strings (not valid JSON)."""
    return (s or "").replace("\\'", "'")


def slice_first_balanced_json_object(text: str) -> str | None:
    """Return the first top-level ``{ ... }`` span, respecting JSON string quotes and escapes."""
    n = len(text)
    i = 0
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        in_str = False
        escape = False
        while j < n:
            ch = text[j]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                j += 1
                continue
            if ch == '"':
                in_str = True
                j += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
            j += 1
        i += 1
    return None


def parse_first_json_dict_from_llm_text(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in *text*, or ``None`` if none can be parsed as a dict."""
    raw = (text or "").strip()
    if not raw:
        return None

    def _loads_dict(blob: str) -> dict[str, Any] | None:
        b = blob.strip()
        if not b:
            return None
        for candidate in (b, repair_llm_json_text_escapes(b)):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
            sliced = slice_first_balanced_json_object(candidate)
            if not sliced:
                continue
            for slice_cand in (sliced, repair_llm_json_text_escapes(sliced)):
                try:
                    obj = json.loads(slice_cand)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
        return None

    m = re.search(r"```json\s*([\s\S]+?)\s*```", raw, flags=re.IGNORECASE)
    if m:
        got = _loads_dict(m.group(1))
        if got is not None:
            return got

    m2 = re.search(r"```\s*([\s\S]+?)\s*```", raw)
    if m2:
        got = _loads_dict(m2.group(1))
        if got is not None:
            return got

    sliced3 = slice_first_balanced_json_object(raw)
    if sliced3:
        got = _loads_dict(sliced3)
        if got is not None:
            return got

    dec = json.JSONDecoder()
    for t in (raw, repair_llm_json_text_escapes(raw)):
        i = 0
        while i < len(t):
            if t[i] == "{":
                try:
                    obj, _end = dec.raw_decode(t, i)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
            i += 1

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        chunk = raw[start : end + 1]
        for cand in (chunk, repair_llm_json_text_escapes(chunk)):
            try:
                obj = json.loads(cand)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    return None
