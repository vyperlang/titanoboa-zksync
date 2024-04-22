import sys
from subprocess import Popen

import boa
import pytest
from boa import BoaError
from boa.contracts.base_evm_contract import StackTrace

from boa_zksync.util import find_free_port, stop_subprocess, wait_url

STARTING_SUPPLY = 100


@pytest.fixture(scope="module")
def simple_contract(zksync_env):
    code = """
totalSupply: public(uint256)
balances: HashMap[address, uint256]

@external
def __init__(t: uint256):
    self.totalSupply = t
    self.balances[self] = t

@external
def update_total_supply(t: uint16) -> uint256:
    self.totalSupply += convert(t, uint256)
    return self.totalSupply

@external
def raise_exception(t: uint256):
    raise "oh no!"
"""
    return boa.loads(code, STARTING_SUPPLY, name="SimpleContract")


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY
    simple_contract.update_total_supply(STARTING_SUPPLY * 2)
    assert simple_contract.totalSupply() == STARTING_SUPPLY * 3


def test_blueprint(zksync_env):
    blueprint_code = """
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
    blueprint = boa.loads_partial(
        blueprint_code, name="Blueprint"
    ).deploy_as_blueprint()
    factory = boa.loads(factory_code, name="Factory")

    salt = b"\x00" * 32

    child_contract_address = factory.create_child(blueprint.address, salt, 5)

    # assert child_contract_address == get_create2_address(
    #     blueprint_bytecode, factory.address, salt
    # ).some_function()
    child = boa.loads_partial(blueprint_code).at(child_contract_address)
    assert child.some_function() == 5


def test_blueprint_immutable(zksync_env):
    blueprint_code = """
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
    blueprint = boa.loads_partial(
        blueprint_code, name="blueprint"
    ).deploy_as_blueprint()
    factory = boa.loads(factory_code, name="factory")

    child_contract_address = factory.create_child(blueprint.address, 5)

    child = boa.loads_partial(blueprint_code).at(child_contract_address)
    assert child.some_function() == 5


def test_internal_call(zksync_env):
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
    contract = boa.loads(code)
    assert contract.bar() == 123


def test_stack_trace(zksync_env):
    called_contract = boa.loads(
        """
@internal
@view
def _get_name() -> String[32]:
    assert False, "Test an error"
    return "crvUSD"

@external
@view
def name() -> String[32]:
    return self._get_name()
    """,
        name="CalledContract",
    )
    caller_contract = boa.loads(
        """
interface HasName:
    def name() -> String[32]: view

@external
@view
def get_name_of(addr: HasName) -> String[32]:
    return addr.name()
    """,
        name="CallerContract",
    )

    # boa.reverts does not give us the stack trace, use pytest.raises instead
    with pytest.raises(BoaError) as ctx:
        caller_contract.get_name_of(called_contract)

    (trace,) = ctx.value.args
    assert trace == StackTrace(
        [
            f"  (<CalledContract interface at {called_contract.address}>."
            f"name() -> ['string'])",
            f"  (<CallerContract interface at {caller_contract.address}>."
            f"get_name_of(address) -> ['string'])",
            # MsgValueSimulator
            "   <Unknown contract 0x0000000000000000000000000000000000008009>",
            # AccountCodeStorage
            "   <Unknown contract 0x0000000000000000000000000000000000008002>",
            f"  (<CallerContract interface at {caller_contract.address}>."
            f"get_name_of(address) -> ['string'])",
        ]
    )
