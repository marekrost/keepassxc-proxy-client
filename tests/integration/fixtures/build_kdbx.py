"""Reproducibly build tests/integration/fixtures/test.kdbx.

Run from the repo root: `uv run python tests/integration/fixtures/build_kdbx.py`.

The integration test suite uses the resulting database. The fixture is also
committed so contributors don't strictly need pykeepass to run the suite;
this script exists so the fixture is reproducible from source and easy to
extend when a new test needs a new entry.

Contents (kept in sync with tests/integration/README.md):

  Root
  ├── example.com               (URL: https://example.com, login: alice, password: hunter2)
  ├── duplicate-url-1           (URL: https://dup.example, login: u1, password: p1)
  ├── duplicate-url-2           (URL: https://dup.example, login: u2, password: p2)
  ├── totp-entry                (TOTP secret: JBSWY3DPEHPK3PXP)
  ├── attr-entry                (custom string "KPH: api-key" = "sk-test-1234")
  └── Work/
      └── nested-entry          (URL: https://work.example, login: bob, password: bobpw)

Master password: ``test``.
"""
from pathlib import Path

from pykeepass import create_database


HERE = Path(__file__).resolve().parent
TARGET = HERE / "test.kdbx"
PASSWORD = "test"


def build() -> None:
    if TARGET.exists():
        TARGET.unlink()

    kp = create_database(str(TARGET), password=PASSWORD)

    kp.add_entry(kp.root_group, "example.com", "alice", "hunter2",
                 url="https://example.com")

    kp.add_entry(kp.root_group, "duplicate-url-1", "u1", "p1",
                 url="https://dup.example")
    kp.add_entry(kp.root_group, "duplicate-url-2", "u2", "p2",
                 url="https://dup.example")

    totp_entry = kp.add_entry(kp.root_group, "totp-entry", "totpuser", "totppw",
                              url="https://totp.example",
                              otp="otpauth://totp/test?secret=JBSWY3DPEHPK3PXP&issuer=test")

    attr_entry = kp.add_entry(kp.root_group, "attr-entry", "attruser", "attrpw",
                              url="https://attr.example")
    attr_entry.set_custom_property("KPH: api-key", "sk-test-1234")

    work = kp.add_group(kp.root_group, "Work")
    kp.add_entry(work, "nested-entry", "bob", "bobpw",
                 url="https://work.example")

    kp.save()
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    build()
