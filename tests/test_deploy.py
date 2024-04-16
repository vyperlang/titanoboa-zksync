import os
import sys
from subprocess import Popen

import pytest
from eth_account import Account

from boa_zksync.interpret import loads_zksync
from boa_zksync.util import find_free_port, wait_url, stop_subprocess

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


@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_node = Popen([
        "era_test_node",
        "--port",
        f"{era_port}",
        "run"
    ], stdout=sys.stdout, stderr=sys.stderr)
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)


@pytest.fixture(scope="module")
def simple_contract():
    return loads_zksync(code, STARTING_SUPPLY)


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY
    simple_contract.update_total_supply(STARTING_SUPPLY * 2)
    assert simple_contract.totalSupply() == STARTING_SUPPLY * 3
