"""Verify the `create` + association flow against a real KeePassXC.

This test is the foundation for the others — most of them call the
`saved_association` fixture from this module (via conftest re-export
isn't worth it; instead, downstream tests perform their own association
through the protocol module).
"""
import pytest

from keepassxc_proxy_client import keystore
from keepassxc_proxy_client.protocol import Connection


pytestmark = pytest.mark.integration


def test_associate_and_persist(socket_path, keystore_file, human_step):
    conn = Connection()
    conn.connect(path=socket_path)

    human_step(
        "in the KeePassXC association dialog, type 'integration-test' as the "
        "name and click Allow"
    )
    assert conn.associate() is True

    assoc_id, public_key = conn.dump_associate()
    assert assoc_id
    assert len(public_key) == 32

    keystore.save(str(keystore_file), assoc_id, public_key)
    assert keystore.list_associations(str(keystore_file)) == [assoc_id]


def test_test_associate_against_saved(socket_path, keystore_file, human_step):
    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog")
    conn.associate()
    assoc_id, public_key = conn.dump_associate()
    keystore.save(str(keystore_file), assoc_id, public_key)

    # New connection — this is what a real `get` call does.
    conn2 = Connection()
    conn2.connect(path=socket_path)
    conn2.load_associate(assoc_id, public_key)
    assert conn2.test_associate() is True
