import boa
import pytest
from boa.rpc import EthereumRPC
from eth_account import Account

from boa_zksync.environment import ZksyncEnv


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
def account():
    return Account.from_key(
        "0x3d3cbc973389cb26f657686445bcc75662b415b656078503592ac8c1abb8810e"
    )
