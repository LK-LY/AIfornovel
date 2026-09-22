import json

import pytest

from tools.check_release import check, read_allowlist, scan_text


@pytest.mark.parametrize("text,rule", [
    ("ghp_" + "X" * 30, "github_token"),
    ("sk-" + "Z" * 30, "model_api_key"),
    ("-----BEGIN " + "PRIVATE KEY-----", "private_key"),
    ("C:" + "/Users/" + "synthetic-person/config", "private_profile_path"),
    ("https://chatgpt.com/" + "c/00000000-test", "private_chat_link"),
])
def test_sensitive_patterns_are_rejected_without_echoing_value(text, rule):
    assert rule in scan_text(text)
    assert text not in json.dumps(scan_text(text))


def test_empty_credential_example_is_safe():
    assert scan_text('HERLENS_API_KEY=\n{"access_token": ""}') == []


def test_allowlist_traversal_is_rejected(tmp_path):
    (tmp_path / ".release-files.json").write_text(json.dumps({"files": ["../outside"]}))
    with pytest.raises(ValueError):
        read_allowlist(tmp_path)
    (tmp_path / ".release-files.json").write_text(json.dumps({"files": ["tools/.codex/auth.json"]}))
    with pytest.raises(ValueError):
        read_allowlist(tmp_path)


def test_missing_allowlisted_file_fails_closed(tmp_path):
    (tmp_path / ".release-files.json").write_text(json.dumps({"files": ["missing.py"]}))
    result = check(tmp_path)
    assert not result["ok"]
    assert result["findings"] == [{"path": "missing.py", "rule": "missing_or_unsafe_path"}]
