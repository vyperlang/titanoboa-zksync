import os

import boa
import pytest
from eth_account import Account

import boa_zksync
from boa_zksync import EraTestNode


@pytest.fixture(scope="module")
def zksync_env(account):
    old_env = boa.env
    boa_zksync.set_zksync_test_env()
    boa.env.add_account(account, force_eoa=True)
    yield boa.env
    boa.set_env(old_env)


@pytest.fixture(scope="module")
def zksync_sepolia_fork(account):
    old_env = boa.env
    fork_url = os.getenv("FORK_URL", "https://sepolia.era.zksync.dev")
    boa_zksync.set_zksync_fork(fork_url, block_identifier=1689570)
    boa.env.add_account(account, force_eoa=True)
    yield boa.env
    boa.set_env(old_env)


@pytest.fixture(scope="module")
def account():
    # default rich account from era_test_node
    _public_key, private_key = EraTestNode.TEST_ACCOUNTS[0]
    return Account.from_key(private_key)
