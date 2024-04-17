import sys
from subprocess import Popen

import pytest

from boa import loads, loads_partial
from boa_zksync.util import find_free_port, wait_url, stop_subprocess

STARTING_SUPPLY = 100


@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_node = Popen([
        "era_test_node",
        "--show-calls", 'user',
        "--port",
        f"{era_port}",
        "run"
    ], stdout=sys.stdout, stderr=sys.stderr)
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)


@pytest.fixture(scope="module")
def simple_contract():
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
    return loads(code, STARTING_SUPPLY)


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY
    simple_contract.update_total_supply(STARTING_SUPPLY * 2)
    assert simple_contract.totalSupply() == STARTING_SUPPLY * 3


def test_blueprint():
    blueprint_code = f"""
val: public(uint256)

@external
def __init__(val: uint256):
    self.val = val

@external
@view
def some_function() -> uint256:
    return self.val
"""

    factory_code = """
@external
def create_child(blueprint: address, salt: bytes32, val: uint256) -> address:
    return create_from_blueprint(blueprint, val, salt=salt)
"""
    blueprint = loads_partial(blueprint_code).deploy_as_blueprint()
    factory = loads(factory_code)

    salt = b"\x00" * 32

    child_contract_address = factory.create_child(blueprint.address, salt, 5)

    # assert child_contract_address == get_create2_address(
    #     blueprint_bytecode, factory.address, salt
    # ).some_function()
    child = loads_partial(blueprint_code).at(child_contract_address)
    assert child.some_function() == 5


def test_blueprint_immutable():
    blueprint_code = f"""
VAL: immutable(uint256)

@external
def __init__(val: uint256):
    VAL = val

@external
@view
def some_function() -> uint256:
    return VAL
"""

    factory_code = """
@external
def create_child(blueprint: address, val: uint256) -> address:
    return create_from_blueprint(blueprint, val)
"""
    blueprint = loads_partial(blueprint_code).deploy_as_blueprint()
    factory = loads(factory_code)

    child_contract_address = factory.create_child(blueprint.address, 5)

    child = loads_partial(blueprint_code).at(child_contract_address)
    assert child.some_function() == 5


def test_internal_call():
    code = """
@internal
@view
def foo() -> uint256:
    return 123

@external
@view
def bar() -> uint256:
    return self.foo()
    """
    contract = loads(code)
    assert contract.bar() == 123
