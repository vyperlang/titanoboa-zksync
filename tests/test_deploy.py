import boa
import pytest
from boa import BoaError
from boa.contracts.base_evm_contract import StackTrace

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
            "  Test an error(<CalledContract interface at "
            f"{called_contract.address}>.name() -> ['string'])",
            "  Test an error(<CallerContract interface at "
            f"{caller_contract.address}>.get_name_of(address) -> "
            "['string'])",
            "   <Unknown contract 0x0000000000000000000000000000000000008009>",
            "   <Unknown contract 0x0000000000000000000000000000000000008002>",
            "  Test an error(<CallerContract interface at "
            f"{caller_contract.address}>.get_name_of(address) -> "
            "['string'])",
        ]
    )


def test_private(zksync_env):
    code = """
bar: uint256
map: HashMap[uint256, uint256]
list: uint256[2]

@internal
def foo(x: uint256) -> uint256:
    self.bar = x
    self.map[0] = x
    self.list[0] = x
    return x
"""
    contract = boa.loads(code)
    assert contract._storage.bar.get() == 0
    assert contract._storage.map.get(0) == 0
    assert contract._storage.list.get() == [0, 0]
    assert contract.internal.foo(123) == 123
    assert contract._storage.bar.get() == 123
    assert contract._storage.map.get(0) == 123
    assert contract._storage.list.get() == [123, 0]
    assert contract.eval("self.bar = 456") is None
    assert contract.eval("self.bar") == 456


def test_logs(zksync_env):
    code = """
event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

@external
def __init__(supply: uint256):
    log Transfer(empty(address), msg.sender, supply)

@external
def transfer(_to : address, _value : uint256) -> bool:
    log Transfer(msg.sender, _to, _value)
    return True
"""
    contract = boa.loads(code, 100)
    assert [str(e) for e in contract.get_logs()] == [
        "Transfer(sender=0x0000000000000000000000000000000000000000, "
        "receiver=0xBC989fDe9e54cAd2aB4392Af6dF60f04873A033A, value=100)"
    ]

    to = boa.env.generate_address()
    contract.transfer(to, 10)
    assert [str(e) for e in contract.get_logs()] == [
        f"Transfer(sender={boa.env.eoa}, receiver={to}, value=10)"
    ]


def test_time(zksync_env):
    code = """
@external
@view
def get_time() -> uint256:
    return block.timestamp
"""
    contract = boa.loads(code)
    assert contract.get_time() == boa.env.vm.state.timestamp
    boa.env.vm.state.timestamp = 1234567890
    assert contract.get_time() == 1234567890
