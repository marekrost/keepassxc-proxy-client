"""TOTP retrieval. The fixture's `totp-entry` carries a known seed."""
import re

import pytest

from keepassxc_proxy_client.protocol import Connection


pytestmark = pytest.mark.integration


@pytest.fixture
def associated(socket_path, human_step):
    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog (totp suite)")
    conn.associate()
    return conn


def test_get_totp_for_entry(associated):
    entries = associated.get_logins("https://totp.example")
    assert entries, "totp-entry not visible — does the association have URL access?"
    uuid = entries[0]["uuid"]

    totp = associated.get_totp(uuid)
    assert totp, "no TOTP returned"
    assert re.fullmatch(r"\d{6}", totp), f"unexpected TOTP shape: {totp!r}"
