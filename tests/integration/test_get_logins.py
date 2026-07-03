"""URL-based lookup against the fixture database.

The fixture has:
  - example.com   (https://example.com, alice / hunter2)
  - dup.example   x2 entries (u1/p1, u2/p2) — exercises multi-match
  - work.example  (nested under Work group)
"""
import pytest

from keepassxc_proxy_client.protocol import Connection


pytestmark = pytest.mark.integration


@pytest.fixture
def associated(socket_path, human_step):
    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog (get-logins suite)")
    conn.associate()
    return conn


def test_get_logins_single_match(associated):
    entries = associated.get_logins("https://example.com")
    assert entries
    matches = [e for e in entries if e.get("login") == "alice"]
    assert matches, f"alice not in entries: {entries}"
    assert matches[0]["password"] == "hunter2"


def test_get_logins_multi_match(associated):
    entries = associated.get_logins("https://dup.example")
    assert entries
    logins = sorted(e.get("login") for e in entries)
    assert logins == ["u1", "u2"]


def test_get_logins_no_match(associated):
    entries = associated.get_logins("https://does-not-exist.example")
    assert entries is False or entries == []
