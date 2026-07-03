"""Path-based lookup — exercises `get-database-entries`.

Requires "Allow access to entries" in KeePassXC's Browser Integration
settings for the test association. The human_step prompts walk the
operator through enabling it.
"""
import pytest

from keepassxc_proxy_client.protocol import Connection


pytestmark = pytest.mark.integration


@pytest.fixture
def associated_with_entries_access(socket_path, human_step):
    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog (get-by-path suite)")
    conn.associate()
    human_step(
        "in KeePassXC → Database → Database Settings → Browser Integration → "
        "select the 'integration-test' association and tick 'Allow access to "
        "entries', then click OK"
    )
    return conn


def _find(entries, path):
    for e in entries:
        group = (e.get("group") or "").rstrip("/")
        title = e.get("title") or ""
        full = f"{group}/{title}" if group else title
        if full == path:
            return e
    return None


def test_get_entry_at_root(associated_with_entries_access):
    resp = associated_with_entries_access.get_database_entries()
    entries = resp.get("entries") or []
    e = _find(entries, "Root/example.com") or _find(entries, "example.com")
    assert e, f"example.com not in entries: {entries}"


def test_get_nested_entry(associated_with_entries_access):
    resp = associated_with_entries_access.get_database_entries()
    entries = resp.get("entries") or []
    e = _find(entries, "Work/nested-entry") or _find(entries, "Root/Work/nested-entry")
    assert e, f"Work/nested-entry not in entries: {entries}"
