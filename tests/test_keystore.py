import base64
import json
import os
import platform
import stat
from unittest.mock import patch

import pytest

from keepassxc_proxy_client import keystore


def test_default_path_uses_platformdirs():
    platformdirs = pytest.importorskip("platformdirs")
    fake_dir = "/fake/config/keepassxc-proxy-client"
    with patch.object(platformdirs, "user_config_dir", return_value=fake_dir) as m:
        path = keystore.default_path()
    m.assert_called_once_with("keepassxc-proxy-client", appauthor=False, roaming=True)
    assert path == os.path.join(fake_dir, "keys.json")


def test_default_path_raises_when_platformdirs_missing():
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "platformdirs":
            raise ImportError("not installed")
        return real_import(name, *a, **kw)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(keystore.KeystoreError):
            keystore.default_path()


def test_read_or_empty_returns_empty_on_missing(tmp_path):
    data = keystore.read_or_empty(str(tmp_path / "nope.json"))
    assert data == {"version": 1, "associations": {}}


def test_read_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        keystore.read(str(tmp_path / "nope.json"))


def test_read_rejects_wrong_version(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps({"version": 99, "associations": {}}))
    with pytest.raises(keystore.KeystoreFormatError):
        keystore.read(str(p))


def test_read_rejects_legacy_single_association_format(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps({
        "name": "legacy-name",
        "public_key": base64.b64encode(b"\x01" * 32).decode("ascii"),
    }))
    with pytest.raises(keystore.KeystoreFormatError):
        keystore.read(str(p))


def test_read_rejects_nested_object_value(tmp_path):
    # The old (nested) schema where values were {"id":..., "key":...} is no longer valid.
    p = tmp_path / "k.json"
    p.write_text(json.dumps({"version": 1, "associations": {"x": {"id": "x", "key": "abc"}}}))
    with pytest.raises(keystore.KeystoreFormatError):
        keystore.read(str(p))


def test_save_creates_file_with_0600(tmp_path):
    p = tmp_path / "sub" / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    assert p.exists()
    if platform.system() != "Windows":
        mode = stat.S_IMODE(p.stat().st_mode)
        assert mode == 0o600
        parent_mode = stat.S_IMODE(p.parent.stat().st_mode)
        assert parent_mode == 0o700


def test_save_round_trip(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\xab" * 32)
    key = keystore.load(str(p), "alpha-id")
    assert key == b"\xab" * 32


def test_save_refuses_overwrite_without_force(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    with pytest.raises(keystore.AssociationExists):
        keystore.save(str(p), "alpha-id", b"\x02" * 32)


def test_save_overwrites_with_force(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    keystore.save(str(p), "alpha-id", b"\x02" * 32, force=True)
    key = keystore.load(str(p), "alpha-id")
    assert key == b"\x02" * 32


def test_save_preserves_other_associations(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    keystore.save(str(p), "beta-id", b"\x02" * 32)
    assert keystore.list_associations(str(p)) == ["alpha-id", "beta-id"]


def test_load_missing_association_raises(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    with pytest.raises(keystore.AssociationNotFound):
        keystore.load(str(p), "ghost")


def test_delete_removes_association(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    keystore.save(str(p), "beta-id", b"\x02" * 32)
    keystore.delete(str(p), "alpha-id")
    assert keystore.list_associations(str(p)) == ["beta-id"]


def test_delete_missing_raises(tmp_path):
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    with pytest.raises(keystore.AssociationNotFound):
        keystore.delete(str(p), "ghost")


def test_list_empty_on_missing_file(tmp_path):
    p = tmp_path / "nope.json"
    assert keystore.list_associations(str(p)) == []


def test_on_disk_format_is_flat(tmp_path):
    """The keystore stores `{id: base64-key}` directly, no nested objects."""
    p = tmp_path / "k.json"
    keystore.save(str(p), "alpha-id", b"\x01" * 32)
    data = json.loads(p.read_text())
    assert data["version"] == 1
    assert data["associations"] == {
        "alpha-id": base64.b64encode(b"\x01" * 32).decode("ascii"),
    }
