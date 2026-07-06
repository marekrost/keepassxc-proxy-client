import json
import sys

import keepassxc_proxy_client.protocol
from keepassxc_proxy_client import keystore


def cmd_create(args):
    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.associate()

    if not connection.test_associate():
        print("For some reason the newly created association is invalid, this should not be happening")
        sys.exit(1)

    name, public_key = connection.dump_associate()
    print(json.dumps(keystore.dump_association(name, public_key)))


def cmd_get(args):
    name, public_key = keystore.load_association(args.file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    if not connection.test_associate():
        print("The loaded association is invalid")
        sys.exit(1)

    logins = connection.get_logins(args.url)
    if not logins:
        print("No logins found for the given URL")
        sys.exit(1)

    print(logins[0]["password"])


def cmd_totp(args):
    name, public_key = keystore.load_association(args.file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    if not connection.test_associate():
        print("The loaded association is invalid")
        sys.exit(1)

    totp_value = connection.get_totp(args.uuid)
    if not totp_value:
        print("No totp found for the given UUID")
        sys.exit(1)

    print(totp_value)


def cmd_unlock(args):
    name, public_key = keystore.load_association(args.file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    print(connection.test_associate(True))
