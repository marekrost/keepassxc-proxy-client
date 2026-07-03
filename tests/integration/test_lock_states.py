"""Behavior of an existing association across lock/unlock transitions."""
import pytest

from keepassxc_proxy_client.protocol import (
    Connection,
    ResponseUnsuccesfulException,
)


pytestmark = pytest.mark.integration


def _err_code(exc: ResponseUnsuccesfulException):
    if not exc.args:
        return None
    payload = exc.args[0]
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("errorCode"))
    except (TypeError, ValueError):
        return None


def test_locked_db_reports_error_code_1(socket_path, human_step):
    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog (lock-states suite)")
    conn.associate()
    assoc_id, public_key = conn.dump_associate()

    human_step("in KeePassXC, Database → Lock Databases")

    conn2 = Connection()
    conn2.connect(path=socket_path)
    conn2.load_associate(assoc_id, public_key)

    with pytest.raises(ResponseUnsuccesfulException) as exc_info:
        conn2.test_associate()
    assert _err_code(exc_info.value) == 1


def test_reopen_after_unlock(socket_path, human_step):
    human_step(
        "make sure the database is UNLOCKED (type 'test' in the unlock "
        "dialog if it's showing)"
    )

    conn = Connection()
    conn.connect(path=socket_path)
    human_step("click Allow on the association dialog (lock-states reopen)")
    conn.associate()
    assert conn.test_associate() is True
