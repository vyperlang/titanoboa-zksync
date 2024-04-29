import os

import boa
import pytest
from eth_account import Account

import boa_zksync


@pytest.fixture(scope="module")
def zksync_env(account):
    old_env = boa.env
    boa_zksync.set_zksync_test_env()
    boa.env.add_account(account, force_eoa=True)
    yield boa.env
    boa.set_env(old_env)


@pytest.fixture(scope="module")
def zksync_fork_env(account):
    old_env = boa.env
    fork_url = os.getenv("FORK_URL", "https://sepolia.era.zksync.dev")
    boa_zksync.set_zksync_fork(fork_url)
    boa.env.add_account(account, force_eoa=True)
    yield boa.env
    boa.set_env(old_env)


@pytest.fixture(scope="module")
def account():
    # default rich account from era_test_node
    return Account.from_key(
        "0x3d3cbc973389cb26f657686445bcc75662b415b656078503592ac8c1abb8810e"
    )
