from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from keepassxc_proxy_client import __main__ as cli
from keepassxc_proxy_client.__main__ import build_parser


def test_help_exits_zero(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for sub in ("create", "get", "get-by-path", "totp", "unlock", "list"):
        assert sub in out


def test_missing_subcommand_exits_two():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([])
    assert exc.value.code == 2


def test_unknown_subcommand_exits_two():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["bogus"])
    assert exc.value.code == 2


def test_create_defaults():
    from keepassxc_proxy_client import keystore
    parser = build_parser()
    args = parser.parse_args(["create"])
    assert args.command == "create"
    assert args.save is False
    assert args.force is False
    assert args.file == keystore.default_path()


def test_create_save_force():
    parser = build_parser()
    args = parser.parse_args(["create", "--save", "--force", "--file", "/tmp/k.json"])
    assert args.save is True
    assert args.force is True
    assert args.file == "/tmp/k.json"


def test_get_requires_url():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["get"])

    from keepassxc_proxy_client import keystore
    args = parser.parse_args(["get", "https://example.com"])
    assert args.url == "https://example.com"
    assert args.file == keystore.default_path()
    assert args.id is None


def test_get_with_id_and_file():
    parser = build_parser()
    args = parser.parse_args(
        ["get", "--file", "/tmp/k.json", "--id", "mydb", "https://example.com"]
    )
    assert args.file == "/tmp/k.json"
    assert args.id == "mydb"


def test_get_field_default_is_password():
    parser = build_parser()
    args = parser.parse_args(["get", "https://example.com"])
    assert args.field == "password"


def test_get_field_can_be_overridden():
    parser = build_parser()
    args = parser.parse_args(["get", "--field", "username", "https://example.com"])
    assert args.field == "username"

    args = parser.parse_args(["get", "-F", "attr:api-token", "https://example.com"])
    assert args.field == "attr:api-token"


def test_get_all_defaults_false():
    parser = build_parser()
    args = parser.parse_args(["get", "https://example.com"])
    assert args.all is False


def test_get_all_can_be_set():
    parser = build_parser()
    args = parser.parse_args(["get", "--all", "https://example.com"])
    assert args.all is True

    args = parser.parse_args(["get", "-a", "https://example.com"])
    assert args.all is True


def test_totp_requires_uuid():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["totp"])
    args = parser.parse_args(["totp", "uuid-123"])
    assert args.uuid == "uuid-123"


def test_unlock_no_required_positional():
    parser = build_parser()
    args = parser.parse_args(["unlock"])
    assert args.command == "unlock"


def test_get_by_path_requires_path():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["get-by-path"])
    args = parser.parse_args(["get-by-path", "Root/Work/AWS/prod root"])
    assert args.command == "get-by-path"
    assert args.path == "Root/Work/AWS/prod root"
    assert args.field == "password"
    assert args.all is False
    assert args.id is None


def test_get_by_path_flags():
    parser = build_parser()
    args = parser.parse_args([
        "get-by-path",
        "--id", "work",
        "--field", "username",
        "--all",
        "/Root/x/y",
    ])
    assert args.id == "work"
    assert args.field == "username"
    assert args.all is True
    assert args.path == "/Root/x/y"


def test_list_subcommand():
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert args.command == "list"


def test_main_dispatches_to_func():
    fake_func = MagicMock()
    fake_args = SimpleNamespace(func=fake_func, debug=False)

    with patch.object(cli, "build_parser") as bp:
        bp.return_value.parse_args.return_value = fake_args
        cli.main()

    fake_func.assert_called_once_with(fake_args)


# ---- exit-code mapping ----

import pytest as _pytest  # noqa: E402
from keepassxc_proxy_client.errors import (  # noqa: E402
    AssociationFailed,
    ProxyClientError,
    DatabaseLocked,
    EntryNotFound,
    FieldMissing,
    ProtocolError,
    SocketUnavailable,
)


@_pytest.mark.parametrize("exc,code", [
    (SocketUnavailable("x"), 10),
    (DatabaseLocked("x"), 11),
    (AssociationFailed("x"), 12),
    (EntryNotFound("x"), 13),
    (FieldMissing("x"), 14),
    (ProtocolError("x"), 20),
    (ProxyClientError("x"), 1),
])
def test_main_maps_exception_to_exit_code(exc, code, capsys):
    fake_func = MagicMock(side_effect=exc)
    fake_args = SimpleNamespace(func=fake_func, debug=False)

    with patch.object(cli, "build_parser") as bp:
        bp.return_value.parse_args.return_value = fake_args
        with _pytest.raises(SystemExit) as ei:
            cli.main()
    assert ei.value.code == code
    err = capsys.readouterr().err
    assert "x" in err
    assert "Traceback" not in err  # debug not set → no traceback


def test_main_debug_prints_traceback(capsys):
    fake_func = MagicMock(side_effect=EntryNotFound("nope"))
    fake_args = SimpleNamespace(func=fake_func, debug=True)

    with patch.object(cli, "build_parser") as bp:
        bp.return_value.parse_args.return_value = fake_args
        with _pytest.raises(SystemExit) as ei:
            cli.main()
    assert ei.value.code == 13
    assert "Traceback" in capsys.readouterr().err


def test_socket_flag_default_and_passthrough():
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert args.socket is None
    args = parser.parse_args(["--socket", "/tmp/sock", "list"])
    assert args.socket == "/tmp/sock"


def test_debug_flag_default_and_passthrough():
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert args.debug is False
    args = parser.parse_args(["--debug", "list"])
    assert args.debug is True
