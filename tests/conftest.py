import os
import sys
from subprocess import Popen

import boa
import pytest
from eth_account import Account

from boa_zksync.util import find_free_port, wait_url, stop_subprocess


@pytest.fixture(scope="module")
def zksync_env(era_test_node, account):
    old_env = boa.env
    boa.set_zksync_env(era_test_node)
    boa.env.add_account(account)
    yield boa.env
    boa.set_env(old_env)


@pytest.fixture(scope="module")
def zksync_fork_env(account):
    old_env = boa.env
    fork_url = os.getenv("FORK_URL", "https://sepolia.era.zksync.dev")
    boa.set_zksync_fork(fork_url)
    boa.env.add_account(account)
    yield boa.env
    boa.set_env(old_env)


@pytest.fixture(scope="module")
def account():
    return Account.from_key(
        "0x3d3cbc973389cb26f657686445bcc75662b415b656078503592ac8c1abb8810e"
    )


@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_node = Popen(
        ["era_test_node", "--show-calls", "user", "--port", f"{era_port}", "run"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)
