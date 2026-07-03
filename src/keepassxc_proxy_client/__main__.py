import sys

from keepassxc_proxy_client import commands

USAGE = """usage: keepassxc_proxy_client

keepassxc_proxy_client create: Connects to a locally running keepassxc instance,
creates a new association with it (this will prompt a dialogue from keepassxc)
and prints it to stdout as JSON. Note that the public key that is printed is
secret and can allow anyone with access to your local machine access to all
passwords that are related to a URL, thus it should be stored safely.

keepassxc_proxy_client get <file> <url>: Reads a keepassxc association from
<file> and attempts to get the first password for <url>. Will exit with 1 if the
association is not valid for the running keepassxc instance or the no logins are
found for the given URL.

keepassxc_proxy_client totp <file> <uuid>: Reads a keepassxc association from
<file> and attempts to get the current totp for <uuid>. Will exit with 1 if the
association is not valid for the running keepassxc instance or the no totp is
found for the given UUID.

keepassxc_proxy_client unlock <file>: Causes a running KeepassXC instance
to launch a dialogue window to allow the user to unlock a locked database.
If the database is already unlocked it has no effect.
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help", "help", "h"]:
        print(USAGE)
        sys.exit(0)

    command = sys.argv[1]

    if command == "create":
        sys.exit(commands.create())
    elif command == "get":
        if len(sys.argv) < 4:
            print("Too little arguments provided, see --help for usage")
            sys.exit(1)
        sys.exit(commands.get(sys.argv[2], sys.argv[3]))
    elif command == "totp":
        if len(sys.argv) < 4:
            print("Too little arguments provided, see --help for usage")
            sys.exit(1)
        sys.exit(commands.totp(sys.argv[2], sys.argv[3]))
    elif command == "unlock":
        if len(sys.argv) < 3:
            print("Too few arguments provided, see --help for usage")
            sys.exit(1)
        sys.exit(commands.unlock(sys.argv[2]))
    else:
        print("Unkown subcommand, see --help for usage")
        sys.exit(1)
