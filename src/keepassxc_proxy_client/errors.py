"""Typed exception hierarchy and CLI exit-code mapping.

Each subclass carries a documented `exit_code` that `__main__.main()` maps to
when the exception escapes a `cmd_*` handler. The numeric range starts at 10
to leave 0/1/2 for shell conventions (argparse already uses 2 for invalid
arguments).

These exceptions are additive — they do not replace upstream's
`ResponseUnsuccesfulException`, which protocol-level code still raises (and
which the typed CLI exceptions sometimes wrap).
"""


class ProxyClientError(Exception):
    """Base class for all CLI-mapped errors. Default exit code is 1."""

    exit_code = 1


class SocketUnavailable(ProxyClientError):
    """Socket missing, refused, or unreachable.

    Typical causes: KeePassXC is not running, browser integration is
    disabled, or the socket lives inside a Flatpak sandbox.
    """

    exit_code = 10


class DatabaseLocked(ProxyClientError):
    """No `.kdbx` is currently unlocked under the chosen association."""

    exit_code = 11


class AssociationFailed(ProxyClientError):
    """`test-associate` failed.

    The stored association is revoked, the wrong database is unlocked, or
    no association exists under this id at all. Also raised when multiple
    databases respond ambiguously to the same association.
    """

    exit_code = 12


class EntryNotFound(ProxyClientError):
    """The requested entry (by URL or by path) does not exist."""

    exit_code = 13


class FieldMissing(ProxyClientError):
    """The matched entry has no value for the requested `--field`."""

    exit_code = 14


class ProtocolError(ProxyClientError):
    """Catch-all for handshake / decrypt / malformed-response failures."""

    exit_code = 20
