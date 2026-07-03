"""Trigger-unlock dialog. Requires the human to lock the DB first."""
import pytest

from keepassxc_proxy_client.protocol import (
    Connection,
    ResponseUnsuccesfulException,
)


pytestmark = pytest.mark.integration


def test_trigger_unlock_when_locked(socket_path, human_step):
    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog (unlock suite)")
    conn.associate()
    assoc_id, public_key = conn.dump_associate()

    human_step("in KeePassXC, Database → Lock Databases")

    # New connection — same pattern as the CLI's `unlock` command.
    conn2 = Connection()
    conn2.connect(path=socket_path)
    conn2.load_associate(assoc_id, public_key)

    # test_associate(True) requests the unlock dialog. We expect an
    # errorCode 1 ("database not opened") response, which the CLI maps to
    # "False" — we just need to verify the protocol-level exception fires.
    with pytest.raises(ResponseUnsuccesfulException):
        conn2.test_associate(trigger_unlock=True)

    human_step("the unlock dialog should be visible — type 'test' and click OK")
