# keepassxc-proxy-client

A Python library and CLI for fetching information from a running KeePassXC
instance through its Browser Integration protocol.

## Requirements

- Python 3.9+.
- KeePassXC with **Browser Integration** enabled in
  Settings → Browser Integration → "Enable browser integration". The
  per-browser checkboxes below do not need to be checked; the master toggle is
  what matters.
- A `.kdbx` unlocked in KeePassXC at the moment the client runs.

## Installation

```bash
# As a one-off tool, no checkout required:
uvx keepassxc-proxy-client --help

# As a project dependency:
pip install keepassxc-proxy-client

# For local development:
git clone <repository-url>
cd keepassxc-proxy-client
uv sync
uv run pytest
```

## Library use

The protocol is exposed into a separate package file for easy use.

### Basic round trip

```python
import keepassxc_proxy_client.protocol

connection = keepassxc_proxy_client.protocol.Connection()
connection.connect()

print(connection.get_databasehash())
# Triggers a "Save key to database?" dialog inside KeePassXC.
connection.associate()
connection.test_associate()

print(connection.get_logins("https://github.com"))
```

The URL passed to `get_logins` **must include a scheme** (`https://...`).
`get_logins("github.com")` returns nothing even if the stored entry's URL field
is literally `github.com`.

### Persist and reuse an association

```python
import keepassxc_proxy_client.protocol

connection = keepassxc_proxy_client.protocol.Connection()
connection.connect()
connection.associate()
assoc_id, public_key = connection.dump_associate()
# ... store assoc_id + public_key somewhere safe ...

# Later, in a fresh process:
connection = keepassxc_proxy_client.protocol.Connection()
connection.connect()
connection.load_associate(assoc_id, public_key)
assert connection.test_associate()
```

The `idKey` (the bytes returned by `dump_associate`) is sensitive: anyone with
it can fetch any password the association is allowed to see. Treat it like a
credential.

### Use the bundled keystore

For callers that want the same on-disk format the CLI uses:

```python
from keepassxc_proxy_client import keystore

path = keystore.default_path()  # OS-appropriate, via platformdirs
keystore.save(path, assoc_id, public_key, force=False)

# Later:
for stored_id in keystore.list_associations(path):
    key_bytes = keystore.load(path, stored_id)
    # ... use with Connection.load_associate(...)
```

### Typed errors

```python
from keepassxc_proxy_client.errors import (
    ProxyClientError,        # base class
    SocketUnavailable,       # KeePassXC not reachable
    DatabaseLocked,          # no .kdbx unlocked
    AssociationFailed,       # bad/missing/revoked association
    EntryNotFound,           # no matching entry
    FieldMissing,            # entry matched but field absent
    ProtocolError,           # handshake / decrypt / malformed response
)
```

These are raised by the CLI command layer (`keepassxc_proxy_client.commands`).
The protocol layer raises `ResponseUnsuccesfulException` (from
`keepassxc_proxy_client.protocol`) on wire-level failures.

## CLI

```text
$ keepassxc_proxy_client --help
usage: keepassxc_proxy_client [-h] [--socket PATH] [--debug] <command> ...

  create       Create a new association with a running KeePassXC instance.
  get          Get a field for an entry matched by URL.
  get-by-path  Get a field for an entry matched by group/title path.
  totp         Get the current TOTP for an entry UUID.
  unlock       Ask KeePassXC to prompt the user to unlock a database.
  list         List association ids stored in the keystore.
```

Global flags: `--socket PATH` overrides the auto-detected socket path;
`--debug` prints a Python traceback alongside the one-line error message.

### Quick start

```bash
# 1. Authorize this client against the unlocked .kdbx.
#    KeePassXC will open a "Save key to database?" dialog.
$ keepassxc_proxy_client create --save
saved association id 'my-laptop' to /home/marek/.config/keepassxc-proxy-client/keys.json

# 2. Read a password by URL.
$ keepassxc_proxy_client get https://github.com
hunter2

# 3. Read a non-URL secret by tree path.
$ keepassxc_proxy_client get-by-path "Root/Work/AWS/prod root" --field uuid
abc-1234-...
```

### `--field`

`get` and `get-by-path` accept `--field` (case-insensitive):

| Field                   | Source                                              |
|-------------------------|-----------------------------------------------------|
| `password` (default)    | entry's password                                    |
| `login` or `username`   | entry's login                                       |
| `name` or `title`       | entry's title                                       |
| `uuid`                  | entry's UUID                                        |
| `attr:<KEY>`            | KeePassXC custom string attribute (`KPH: <KEY>`)    |

`url` and `notes` are intentionally not exposed via `get`, since KeePassXC's
`get-logins` action does not return them. `get-by-path` calls
`get-database-entries` instead, which has access to richer data — but it
requires you to enable **"Allow access to entries"** for the chosen
association in KeePassXC's Browser Integration settings.

### Multi-database workflow

The keystore can hold associations for several `.kdbx` files. Each is keyed
by the association id KeePassXC returned at `create --save` time.

```bash
# Authorize against a second .kdbx (different id).
$ keepassxc_proxy_client create --save
saved association id 'work-vault' to ...

$ keepassxc_proxy_client list
my-laptop
work-vault

# Pick which one to use explicitly:
$ keepassxc_proxy_client get --id work-vault https://internal.example.com
...

# Or omit --id and let the client try each until one authenticates.
# Useful when only one .kdbx is unlocked at a time.
$ keepassxc_proxy_client get https://internal.example.com
...
```

`create --save` refuses to overwrite an existing id; pass `--force` to rotate
an existing entry to a new idKey.

### Multi-match handling

If `get`/`get-by-path` resolves to multiple entries, the default prints the
first match's field and emits a one-line warning to stderr. Pass `--all` to
print every match (one value per line, no warning).

### Exit codes

Downstream automation can rely on these:

| Exit code | Exception (in `keepassxc_proxy_client.errors`) | Meaning                                                                    |
|-----------|------------------------------------------------|----------------------------------------------------------------------------|
| 0         | —                                              | Success.                                                                   |
| 1         | `ProxyClientError` (base)                      | Generic fallback for failures that don't fit a more specific class.        |
| 2         | (argparse)                                     | Invalid command-line arguments.                                            |
| 10        | `SocketUnavailable`                            | Socket missing / refused / `EACCES` (Flatpak).                             |
| 11        | `DatabaseLocked`                               | No `.kdbx` unlocked under any stored association.                          |
| 12        | `AssociationFailed`                            | Keystore problem or `test-associate` failed for non-lock reasons.          |
| 13        | `EntryNotFound`                                | No matching entry (or `get-totp` returned empty).                          |
| 14        | `FieldMissing`                                 | Entry matched but the requested `--field` is absent.                       |
| 20        | `ProtocolError`                                | Handshake / decrypt / malformed response, or any unclassified protocol fault. |

Every error writes a one-line, human-readable explanation to stderr. Add
`--debug` to also print a Python traceback.

### Keystore location

The on-disk keystore is resolved via
[`platformdirs`](https://pypi.org/project/platformdirs/):

| OS          | Default path                                                                                            |
|-------------|---------------------------------------------------------------------------------------------------------|
| Linux / BSD | `$XDG_CONFIG_HOME/keepassxc-proxy-client/keys.json` (else `~/.config/keepassxc-proxy-client/keys.json`) |
| macOS       | `~/Library/Application Support/keepassxc-proxy-client/keys.json`                                        |
| Windows     | `%APPDATA%\keepassxc-proxy-client\keys.json`                                                            |

On POSIX the directory is created `0700` and the file written `0600`. Pass
`--file PATH` to point any subcommand at a different location.

### Flatpak note

If KeePassXC was installed as a Flatpak, its Browser Integration socket lives
inside the sandbox and is unreachable to non-Flatpak clients. The CLI will
exit `10` with a message pointing at this. Either install the native KeePassXC
package, or run this client through `flatpak-spawn`.

## Project layout

```
src/keepassxc_proxy_client/
  protocol.py     # Connection + ResponseUnsuccesfulException (wire protocol)
  keystore.py     # on-disk association store
  errors.py       # ProxyClientError hierarchy + exit codes
  commands.py     # cmd_* handlers (cli logic)
  __main__.py     # argparse wiring + main()
```

## License

0BSD. See [`LICENSE`](LICENSE).
