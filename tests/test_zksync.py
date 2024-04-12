import socket
import sys
from subprocess import Popen, TimeoutExpired
from time import sleep

import boa
import pytest
import requests
from boa.rpc import EthereumRPC
from eth_account import Account
from requests.exceptions import ConnectionError

from boa_zksync.env import ZksyncEnv
from boa_zksync.interpret import loads_zksync

code = """
totalSupply: public(uint256)
balances: HashMap[address, uint256]

@external
def __init__(t: uint256):
    self.totalSupply = t
    self.balances[self] = t

@external
def update_total_supply(t: uint16):
    self.totalSupply += convert(t, uint256)

@external
def raise_exception(t: uint256):
    raise "oh no!"
"""

STARTING_SUPPLY = 100


def find_free_port():
    # https://gist.github.com/bertjwregeer/0be94ced48383a42e70c3d9fff1f4ad0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 0))
    portnum = s.getsockname()[1]
    s.close()
    return portnum


@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_cmd = f"era_test_node --port {era_port} run".split(" ")
    era_node = Popen(era_cmd, stdout=sys.stdout, stderr=sys.stderr)
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)


def wait_url(url: str):
    while True:
        try:
            requests.head(url)
            return url
        except ConnectionError:
            sleep(0.1)


def stop_subprocess(proc: Popen[bytes]):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


@pytest.fixture(scope="module")
def account():
    return Account.from_key(
        "0x3d3cbc973389cb26f657686445bcc75662b415b656078503592ac8c1abb8810e"
    )


@pytest.fixture(scope="module")
def rpc(era_test_node):
    return EthereumRPC(era_test_node)


@pytest.fixture(scope="module", autouse=True)
def zksync_env(rpc, account):
    env = ZksyncEnv(rpc)
    env.add_account(account)
    with boa.swap_env(env):
        yield


@pytest.fixture(scope="module")
def simple_contract():
    return loads_zksync(code, STARTING_SUPPLY)


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY
