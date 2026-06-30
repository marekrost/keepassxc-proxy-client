import base64
import json
import os
import platform
from unittest.mock import patch, MagicMock

import pytest

from keepassxc_proxy_client import protocol


# ---- get_socket_path ----

def test_get_socket_path_linux_no_flatpak(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    with patch.object(protocol.platform, "system", return_value="Linux"):
        path = protocol.Connection.get_socket_path()
    assert path == os.path.join(str(tmp_path), "org.keepassxc.KeePassXC.BrowserServer")


def test_get_socket_path_linux_flatpak_present(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    flatpak_dir = tmp_path / "app" / "org.keepassxc.KeePassXC"
    flatpak_dir.mkdir(parents=True)
    flatpak_socket = flatpak_dir / "org.keepassxc.KeePassXC.BrowserServer"
    flatpak_socket.touch()

    with patch.object(protocol.platform, "system", return_value="Linux"):
        path = protocol.Connection.get_socket_path()

    assert path == str(flatpak_socket)


def test_get_socket_path_darwin(monkeypatch):
    monkeypatch.setenv("TMPDIR", "/var/tmp-test")
    with patch.object(protocol.platform, "system", return_value="Darwin"):
        path = protocol.Connection.get_socket_path()
    assert path == "/var/tmp-test/org.keepassxc.KeePassXC.BrowserServer"


def test_get_socket_path_fallback(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with patch.object(protocol.platform, "system", return_value="Linux"):
        path = protocol.Connection.get_socket_path()
    assert path == "/tmp/org.keepassxc.KeePassXC.BrowserServer"


# ---- Connection construction & misc ----

@pytest.fixture
def conn():
    # __init__ creates a real AF_UNIX socket on Linux but does not connect — safe.
    if platform.system() == "Windows":
        pytest.skip("Windows named-pipe construction not exercised on Linux")
    return protocol.Connection()


def test_change_public_keys_payload_shape(conn):
    payload = conn.change_public_keys()
    assert payload["action"] == "change-public-keys"
    assert payload["clientID"] == conn.client_id
    # publicKey and nonce are base64 of 32 and 24 bytes respectively
    assert len(base64.b64decode(payload["publicKey"])) == 32
    assert len(base64.b64decode(payload["nonce"])) == 24


def test_load_dump_associate_round_trip(conn):
    raw_key = b"\xab" * 32
    conn.load_associate("my-id", raw_key)
    name, key = conn.dump_associate()
    assert name == "my-id"
    assert key == raw_key


def test_client_id_is_unique_per_connection():
    if platform.system() == "Windows":
        pytest.skip()
    a = protocol.Connection()
    b = protocol.Connection()
    assert a.client_id != b.client_id


# ---- Encrypted response error path ----

def test_get_encrypted_response_raises_on_error(conn):
    # Force get_unencrypted_response to return a payload containing "error".
    with patch.object(conn, "get_unencrypted_response", return_value={"error": "Database not opened", "errorCode": "1"}):
        with pytest.raises(protocol.ResponseUnsuccesfulException):
            conn.get_encrypted_response()


def test_get_encrypted_response_raises_on_success_false(conn):
    # Build a payload that decodes successfully but reports success: false.
    # We bypass the box decrypt by patching it.
    fake_box = MagicMock()
    fake_box.decrypt.return_value = json.dumps({"success": False}).encode("utf-8")
    conn.box = fake_box

    raw = {
        "nonce": base64.b64encode(b"\x00" * 24).decode("utf-8"),
        "message": base64.b64encode(b"ciphertext").decode("utf-8"),
    }
    with patch.object(conn, "get_unencrypted_response", return_value=raw):
        with pytest.raises(protocol.ResponseUnsuccesfulException):
            conn.get_encrypted_response()


def test_get_encrypted_response_success(conn):
    fake_box = MagicMock()
    fake_box.decrypt.return_value = json.dumps({"success": True, "hello": "world"}).encode("utf-8")
    conn.box = fake_box

    raw = {
        "nonce": base64.b64encode(b"\x00" * 24).decode("utf-8"),
        "message": base64.b64encode(b"ciphertext").decode("utf-8"),
    }
    with patch.object(conn, "get_unencrypted_response", return_value=raw):
        response = conn.get_encrypted_response()
    assert response == {"success": True, "hello": "world"}


# ---- get_logins / get_totp branching ----

def test_get_logins_empty(conn):
    from nacl.public import PrivateKey
    conn.associate_id = "test"
    conn.id_public_key = PrivateKey.generate().public_key
    with patch.object(conn, "send_encrypted_message"), \
         patch.object(conn, "get_encrypted_response", return_value={"count": 0, "entries": []}):
        assert conn.get_logins("https://example.com") is False


def test_get_logins_populated(conn):
    entries = [{"password": "p", "login": "u"}]
    conn.associate_id = "test"
    from nacl.public import PrivateKey
    conn.id_public_key = PrivateKey.generate().public_key

    with patch.object(conn, "send_encrypted_message"), \
         patch.object(conn, "get_encrypted_response", return_value={"count": 1, "entries": entries}):
        assert conn.get_logins("https://example.com") == entries


def test_get_totp_success(conn):
    with patch.object(conn, "send_encrypted_message"), \
         patch.object(conn, "get_encrypted_response", return_value={"success": True, "totp": "987654"}):
        assert conn.get_totp("uuid") == "987654"


def test_get_totp_failure(conn):
    with patch.object(conn, "send_encrypted_message"), \
         patch.object(conn, "get_encrypted_response", return_value={"success": False}):
        assert conn.get_totp("uuid") is False


# ---- send_encrypted_message wraps payload and increments nonce ----

def test_send_encrypted_message_increments_nonce(conn):
    fake_box = MagicMock()
    fake_ct = MagicMock()
    fake_ct.ciphertext = b"abc"
    fake_box.encrypt.return_value = fake_ct
    conn.box = fake_box

    sent = []
    conn.socket = MagicMock()
    conn.socket.sendall.side_effect = lambda b: sent.append(b)

    nonce_before = conn.nonce
    conn.send_encrypted_message({"action": "test-associate"})
    nonce_after = conn.nonce

    assert int.from_bytes(nonce_after, "big") == int.from_bytes(nonce_before, "big") + 1

    msg = json.loads(sent[0].decode("utf-8"))
    assert msg["action"] == "test-associate"
    assert msg["clientID"] == conn.client_id
    assert "message" in msg and "nonce" in msg
    assert "triggerUnlock" not in msg


def test_send_encrypted_message_trigger_unlock(conn):
    fake_box = MagicMock()
    fake_ct = MagicMock()
    fake_ct.ciphertext = b"abc"
    fake_box.encrypt.return_value = fake_ct
    conn.box = fake_box

    sent = []
    conn.socket = MagicMock()
    conn.socket.sendall.side_effect = lambda b: sent.append(b)

    conn.send_encrypted_message({"action": "test-associate"}, trigger_unlock=True)
    msg = json.loads(sent[0].decode("utf-8"))
    assert msg["triggerUnlock"] == "true"
