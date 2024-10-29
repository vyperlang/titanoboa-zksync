import boa
import pytest
from boa import BoaError
from boa.contracts.base_evm_contract import StackTrace
from boa.contracts.call_trace import TraceFrame

from tests.conftest import STARTING_SUPPLY


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY
    simple_contract.update_total_supply(STARTING_SUPPLY * 2)
    assert simple_contract.totalSupply() == STARTING_SUPPLY * 3


def test_blueprint(zksync_env):
    blueprint_code = """
val: public(uint256)

@deploy
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
    child = boa.loads_partial(blueprint_code).at(child_contract_address)
    assert child.some_function() == 5


def test_blueprint_immutable(zksync_env):
    blueprint_code = """
VAL: immutable(uint256)

@deploy
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
    return staticcall addr.name()
    """,
        name="CallerContract",
    )

    # boa.reverts does not give us the stack trace, use pytest.raises instead
    with pytest.raises(BoaError) as ctx:
        caller_contract.get_name_of(called_contract)

    (call_trace, stack_trace) = ctx.value.args
    called_addr = called_contract.address
    assert stack_trace == StackTrace(
        [
            "  Test an error(<CalledContract interface at "
            f"{called_addr}> (file <unknown>).name() -> ['string'])",
            "  Test an error(<CallerContract interface at "
            f"{caller_contract.address}> (file "
            "<unknown>).get_name_of(address) -> ['string'])",
            "   <Unknown contract 0x0000000000000000000000000000000000008009>",
            "   <Unknown contract 0x0000000000000000000000000000000000008002>",
            "  Test an error(<CallerContract interface at "
            f"{caller_contract.address}> (file <unknown>).get_name_of(address) -> "
            "['string'])",
        ]
    )
    assert isinstance(call_trace, TraceFrame)
    assert str(call_trace).split("\n") == [
        f'[E] [24505] CallerContract.get_name_of(addr = "{called_addr}") <0x>',
        "    [E] [23574] Unknown contract 0x0000000000000000000000000000000000008002.0x4de2e468",
        "        [566] Unknown contract 0x000000000000000000000000000000000000800B.0x29f172ad",
        "        [1909] Unknown contract 0x000000000000000000000000000000000000800B.0x06bed036",
        "            [159] Unknown contract 0x0000000000000000000000000000000000008010.0x00000000",
        "        [449] Unknown contract 0x000000000000000000000000000000000000800B.0xa225efcb",
        "        [2226] Unknown contract 0x0000000000000000000000000000000000008002.0x4de2e468",
        "        [427] Unknown contract 0x000000000000000000000000000000000000800B.0xa851ae78",
        "        [398] Unknown contract 0x0000000000000000000000000000000000008004.0xe516761e",
        "        [E] [2548] Unknown contract 0x0000000000000000000000000000000000008009.0xb47fade1",
        f'            [E] [1365] CallerContract.get_name_of(addr = "{called_addr}") <0x>',
        "                [E] [397] CalledContract.name() <0x>",
    ]


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

@deploy
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
