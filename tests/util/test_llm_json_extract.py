"""Tests for ``src.util.llm_json_extract``."""

import json

from src.util.llm_json_extract import (
    parse_first_json_dict_from_llm_text,
    repair_llm_json_text_escapes,
    slice_first_balanced_json_object,
)


def test_slice_first_balanced_respects_strings():
    s = r'prefix {"a": "}", "b": 1} tail'
    assert slice_first_balanced_json_object(s) == r'{"a": "}", "b": 1}'


def test_parse_prefers_json_fence_with_preamble():
    raw = """Sure — here you go.

```json
{"notes": {"foo": "bar"}}
```
"""
    d = parse_first_json_dict_from_llm_text(raw)
    assert d == {"notes": {"foo": "bar"}}


def test_parse_balanced_when_extra_after_closing_brace():
    raw = '{"notes": {"x": "y"}} trailing prose'
    d = parse_first_json_dict_from_llm_text(raw)
    assert d == {"notes": {"x": "y"}}


def test_parse_generic_triple_backtick_fence():
    raw = "Output:\n```\n{\"a\": 1}\n```\n"
    d = parse_first_json_dict_from_llm_text(raw)
    assert d == {"a": 1}


def test_parse_repairs_invalid_backslash_apostrophe_in_strings():
    # \' is not valid JSON; models often emit it for possessives.
    raw = '{"notes": {"google": "Respect Google' + r"\'" + 's brand guidelines."}}'
    assert json.loads(repair_llm_json_text_escapes(raw))["notes"]["google"] == "Respect Google's brand guidelines."
    d = parse_first_json_dict_from_llm_text(raw)
    assert d == {"notes": {"google": "Respect Google's brand guidelines."}}
