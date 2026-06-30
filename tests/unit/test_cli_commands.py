import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from keepassxc_proxy_client import commands as cli
from keepassxc_proxy_client import keystore
from keepassxc_proxy_client.errors import (
    AssociationFailed,
    DatabaseLocked,
    EntryNotFound,
    FieldMissing,
    ProtocolError,
    SocketUnavailable,
)
from keepassxc_proxy_client.protocol import ResponseUnsuccesfulException


def _make_store(tmp_path, associations):
    """Create a keystore file with the given {assoc_id: key_bytes} entries."""
    path = tmp_path / "k.json"
    for assoc_id, key_bytes in associations.items():
        keystore.save(str(path), assoc_id, key_bytes)
    return str(path)


def _ns(**kwargs):
    """Build a SimpleNamespace with `socket` defaulting to None."""
    kwargs.setdefault("socket", None)
    return SimpleNamespace(**kwargs)


# ---- cmd_create ----

@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_create_prints_json_when_not_saving(MockConn, capsys):
    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.dump_associate.return_value = ("assoc-id", b"\x02" * 32)

    cli.cmd_create(_ns(save=False, force=False, file=None))

    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "assoc-id"
    assert base64.b64decode(out["public_key"]) == b"\x02" * 32


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_create_saves_when_flag_set(MockConn, tmp_path, capsys):
    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.dump_associate.return_value = ("new-id", b"\x03" * 32)

    store_path = str(tmp_path / "k.json")
    cli.cmd_create(_ns(save=True, force=False, file=store_path))

    assert keystore.list_associations(store_path) == ["new-id"]
    assert "saved association" in capsys.readouterr().out


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_create_save_refuses_overwrite(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"same-id": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.dump_associate.return_value = ("same-id", b"\x09" * 32)

    with pytest.raises(AssociationFailed, match="already exists"):
        cli.cmd_create(_ns(save=True, force=False, file=store_path))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_create_save_force_overwrites(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"same-id": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.dump_associate.return_value = ("same-id", b"\x09" * 32)

    cli.cmd_create(_ns(save=True, force=True, file=store_path))

    key = keystore.load(store_path, "same-id")
    assert key == b"\x09" * 32


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_create_invalid_association_raises_protocol_error(MockConn):
    instance = MockConn.return_value
    instance.test_associate.return_value = False

    with pytest.raises(ProtocolError):
        cli.cmd_create(_ns(save=False, force=False, file=None))


# ---- cmd_get ----

@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_with_explicit_id(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {
        "db1": b"\x01" * 32,
        "db2": b"\x02" * 32,
    })

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{"password": "s3cret"}]

    cli.cmd_get(_ns(file=store_path, id="db2", url="https://example.com",
                    field="password", all=False))

    instance.load_associate.assert_called_once_with("db2", b"\x02" * 32)
    instance.get_logins.assert_called_once_with("https://example.com")
    assert capsys.readouterr().out.strip() == "s3cret"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_no_id_tries_each_until_one_works(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {
        "db1": b"\x01" * 32,
        "db2": b"\x02" * 32,
    })

    instance = MockConn.return_value
    instance.test_associate.side_effect = [
        ResponseUnsuccesfulException({"error": "not associated", "errorCode": 4}),
        True,
    ]
    instance.get_logins.return_value = [{"password": "yay"}]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field="password", all=False))

    assert instance.load_associate.call_count == 2
    assert capsys.readouterr().out.strip() == "yay"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_no_associations_in_store_raises_assoc_failed(MockConn, tmp_path):
    store_path = str(tmp_path / "k.json")
    keystore.save(store_path, "tmp", b"\x00" * 32)
    keystore.delete(store_path, "tmp")

    with pytest.raises(AssociationFailed, match="no associations"):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_all_associations_locked_raises_database_locked(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32, "db2": b"\x02" * 32})

    instance = MockConn.return_value
    instance.test_associate.side_effect = ResponseUnsuccesfulException(
        {"error": "Database not opened", "errorCode": 1}
    )

    with pytest.raises(DatabaseLocked):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_all_associations_fail_non_lock_raises_assoc_failed(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.side_effect = ResponseUnsuccesfulException(
        {"error": "no match", "errorCode": 4}
    )

    with pytest.raises(AssociationFailed):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_url_not_found_raises_entry_not_found(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = False

    with pytest.raises(EntryNotFound):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_get_logins_errorcode1_treated_as_not_found(MockConn, tmp_path):
    """After a successful test-associate, errorCode 1 from get-logins means no entry."""
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.side_effect = ResponseUnsuccesfulException(
        {"error": "Database not opened", "errorCode": 1}
    )

    with pytest.raises(EntryNotFound):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_unknown_id_raises_assoc_failed(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    with pytest.raises(AssociationFailed, match="not found"):
        cli.cmd_get(_ns(file=store_path, id="ghost", url="https://example.com",
                        field="password", all=False))


# ---- cmd_get --field ----

@pytest.mark.parametrize("field,expected", [
    ("password", "s3cret"),
    ("login", "alice"),
    ("username", "alice"),
    ("name", "Example Login"),
    ("title", "Example Login"),
    ("uuid", "abc-123"),
    ("PASSWORD", "s3cret"),
])
@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_field_direct(MockConn, tmp_path, capsys, field, expected):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{
        "password": "s3cret",
        "login": "alice",
        "name": "Example Login",
        "uuid": "abc-123",
    }]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field=field, all=False))
    assert capsys.readouterr().out.strip() == expected


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_field_attr(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{
        "password": "s3cret",
        "stringFields": [
            {"KPH: api-token": "tok-xyz"},
            {"KPH: env": "prod"},
        ],
    }]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field="attr:api-token", all=False))
    assert capsys.readouterr().out.strip() == "tok-xyz"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_field_attr_missing_raises_field_missing(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{
        "password": "s3cret",
        "stringFields": [{"KPH: env": "prod"}],
    }]

    with pytest.raises(FieldMissing, match="not present"):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="attr:ghost", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_field_unknown_raises_field_missing(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{"password": "s3cret"}]

    with pytest.raises(FieldMissing, match="unknown field"):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="bogus", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_field_missing_on_entry_raises_field_missing(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{"password": "s3cret", "login": "alice"}]

    with pytest.raises(FieldMissing):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="uuid", all=False))


# ---- cmd_get --all / multi-match ----

@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_multi_match_default_picks_first_with_warning(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [
        {"password": "first", "login": "a"},
        {"password": "second", "login": "b"},
    ]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field="password", all=False))
    out = capsys.readouterr()
    assert out.out.strip() == "first"
    assert "2 entries match" in out.err
    assert "--all" in out.err


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_all_prints_each_match(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [
        {"password": "first"}, {"password": "second"}, {"password": "third"},
    ]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field="password", all=True))
    out = capsys.readouterr()
    assert out.out.splitlines() == ["first", "second", "third"]
    assert "entries match" not in out.err


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_all_with_login_field(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [
        {"password": "p1", "login": "alice"},
        {"password": "p2", "login": "bob"},
    ]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field="username", all=True))
    assert capsys.readouterr().out.splitlines() == ["alice", "bob"]


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_all_field_missing_on_any_entry_raises(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [
        {"password": "p1", "uuid": "u1"},
        {"password": "p2"},
    ]

    with pytest.raises(FieldMissing, match="1 of 2"):
        cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                        field="uuid", all=True))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_single_match_no_warning(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_logins.return_value = [{"password": "only"}]

    cli.cmd_get(_ns(file=store_path, id=None, url="https://example.com",
                    field="password", all=False))
    out = capsys.readouterr()
    assert out.out.strip() == "only"
    assert out.err == ""


# ---- cmd_get_by_path ----

_ENTRIES_RESPONSE = {
    "success": True,
    "entries": [
        {"group": "Root/Work/AWS", "title": "prod root",
         "password": "aws-prod-pw", "login": "root", "uuid": "aws-1"},
        {"group": "Root/Work/AWS", "title": "dev root",
         "password": "aws-dev-pw", "login": "root", "uuid": "aws-2"},
        {"group": "Root/Personal", "title": "github",
         "password": "gh-pw", "login": "user", "uuid": "gh-1"},
        {"group": "Root/Work/GCP", "title": "prod root",
         "password": "gcp-prod-pw", "login": "root", "uuid": "gcp-1"},
    ],
}


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_exact_match(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = _ENTRIES_RESPONSE

    cli.cmd_get_by_path(_ns(file=store_path, id=None,
                            path="Root/Work/AWS/prod root",
                            field="password", all=False))
    assert capsys.readouterr().out.strip() == "aws-prod-pw"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_leading_slash_optional(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = _ENTRIES_RESPONSE

    cli.cmd_get_by_path(_ns(file=store_path, id=None,
                            path="/Root/Personal/github",
                            field="login", all=False))
    assert capsys.readouterr().out.strip() == "user"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_not_found_raises_entry_not_found(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = _ENTRIES_RESPONSE

    with pytest.raises(EntryNotFound):
        cli.cmd_get_by_path(_ns(file=store_path, id=None,
                                path="Root/Work/AWS/ghost",
                                field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_case_sensitive(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = _ENTRIES_RESPONSE

    with pytest.raises(EntryNotFound):
        cli.cmd_get_by_path(_ns(file=store_path, id=None,
                                path="root/work/aws/prod root",
                                field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_protocol_error_surfaces_hint(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.side_effect = ResponseUnsuccesfulException(
        {"error": "access denied"}
    )

    with pytest.raises(ProtocolError, match="Allow access to entries"):
        cli.cmd_get_by_path(_ns(file=store_path, id=None,
                                path="Root/Work/AWS/prod root",
                                field="password", all=False))


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_uses_other_field(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = _ENTRIES_RESPONSE

    cli.cmd_get_by_path(_ns(file=store_path, id=None,
                            path="Root/Work/AWS/prod root",
                            field="uuid", all=False))
    assert capsys.readouterr().out.strip() == "aws-1"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_collision_warns_and_picks_first(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    response = {
        "success": True,
        "entries": [
            {"group": "Root/Work/AWS", "title": "prod root",
             "password": "first", "uuid": "1"},
            {"group": "Root/Work/AWS", "title": "prod root",
             "password": "second", "uuid": "2"},
        ],
    }
    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = response

    cli.cmd_get_by_path(_ns(file=store_path, id=None,
                            path="Root/Work/AWS/prod root",
                            field="password", all=False))
    out = capsys.readouterr()
    assert out.out.strip() == "first"
    assert "2 entries match this path" in out.err


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_get_by_path_all(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    response = {
        "success": True,
        "entries": [
            {"group": "Root/Work/AWS", "title": "prod root",
             "password": "first", "uuid": "1"},
            {"group": "Root/Work/AWS", "title": "prod root",
             "password": "second", "uuid": "2"},
        ],
    }
    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_database_entries.return_value = response

    cli.cmd_get_by_path(_ns(file=store_path, id=None,
                            path="Root/Work/AWS/prod root",
                            field="password", all=True))
    out = capsys.readouterr()
    assert out.out.splitlines() == ["first", "second"]
    assert out.err == ""


# ---- cmd_totp ----

@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_totp_success(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_totp.return_value = "123456"

    cli.cmd_totp(_ns(file=store_path, id=None, uuid="entry-uuid"))

    instance.get_totp.assert_called_once_with("entry-uuid")
    assert capsys.readouterr().out.strip() == "123456"


@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_totp_missing_raises_entry_not_found(MockConn, tmp_path):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True
    instance.get_totp.return_value = False

    with pytest.raises(EntryNotFound):
        cli.cmd_totp(_ns(file=store_path, id=None, uuid="entry-uuid"))


# ---- cmd_unlock ----

@patch("keepassxc_proxy_client.protocol.Connection")
def test_cmd_unlock_triggers_unlock(MockConn, tmp_path, capsys):
    store_path = _make_store(tmp_path, {"db1": b"\x01" * 32})

    instance = MockConn.return_value
    instance.test_associate.return_value = True

    cli.cmd_unlock(_ns(file=store_path, id=None))

    instance.test_associate.assert_called_once_with(True)
    assert capsys.readouterr().out.strip() == "True"


# ---- cmd_list ----

def test_cmd_list_outputs_ids(tmp_path, capsys):
    store_path = _make_store(tmp_path, {
        "alpha": b"\x01" * 32,
        "beta": b"\x02" * 32,
    })
    cli.cmd_list(_ns(file=store_path))
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["alpha", "beta"]


def test_cmd_list_empty(tmp_path, capsys):
    store_path = str(tmp_path / "nope.json")
    cli.cmd_list(_ns(file=store_path))
    assert capsys.readouterr().out == ""


# ---- socket-level error mapping ----

@patch("keepassxc_proxy_client.protocol.Connection")
def test_open_connection_eacces_becomes_flatpak_hint(MockConn):
    instance = MockConn.return_value
    instance.connect.side_effect = PermissionError("EACCES")

    with pytest.raises(SocketUnavailable, match="Flatpak"):
        cli._open_connection()


@patch("keepassxc_proxy_client.protocol.Connection")
def test_open_connection_socket_missing_becomes_socket_unavailable(MockConn):
    instance = MockConn.return_value
    instance.connect.side_effect = FileNotFoundError("no socket")

    with pytest.raises(SocketUnavailable, match="KeePassXC"):
        cli._open_connection()


@patch("keepassxc_proxy_client.protocol.Connection")
def test_open_connection_refused_becomes_socket_unavailable(MockConn):
    instance = MockConn.return_value
    instance.connect.side_effect = ConnectionRefusedError("nope")

    with pytest.raises(SocketUnavailable):
        cli._open_connection()


@patch("keepassxc_proxy_client.protocol.Connection")
def test_open_connection_passes_socket_path(MockConn):
    instance = MockConn.return_value
    cli._open_connection(socket_path="/custom/socket")
    instance.connect.assert_called_once_with(path="/custom/socket")
