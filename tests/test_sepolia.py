import boa
import pytest
from boa.rpc import EthereumRPC

import boa_zksync
from boa_zksync import EraTestNode
from boa_zksync.environment import ZERO_ADDRESS


def test_dummy_contract(zksync_sepolia_fork):
    code = """
@external
@view
def foo() -> bool:
    return True
    """
    c = boa.loads_partial(code).at("0xB27cCfd5909f46F5260Ca01BA27f591868D08704")
    assert c.foo() is True
    c = boa.loads(code)
    assert c.foo() is True


@pytest.mark.ignore_isolation
def test_contract_storage(zksync_sepolia_fork):
    code = """
implementation: public(address)

@external
def set_implementation(_implementation: address):
    self.implementation = _implementation
    """
    c = boa.loads(code)
    assert c.implementation() == ZERO_ADDRESS
    boa.env.set_balance(boa.env.eoa, 10**20)
    c.set_implementation(c.address)
    assert c.implementation() == c.address


def test_fork_rpc(zksync_sepolia_fork):
    assert isinstance(boa.env._rpc, EraTestNode)
    assert isinstance(boa.env._rpc.inner_rpc, EthereumRPC)


@pytest.mark.ignore_isolation
def test_real_deploy_and_verify(zksync_sepolia_env):
    from tests.data import Counter

    contract = Counter.deploy()
    verify = boa_zksync.verify(contract)
    verify.wait_for_verification()
    assert verify.is_verified()
