import os
import sys
from subprocess import Popen

import pytest
from eth_account import Account

from boa_zksync.interpret import loads_zksync, loads_zksync_partial
from boa_zksync.util import find_free_port, wait_url, stop_subprocess



@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_node = Popen([
        "era_test_node",
        "--port",
        f"{era_port}",
        "fork",
        os.getenv("FORK_URL", "https://sepolia.era.zksync.dev")
    ], stdout=sys.stdout, stderr=sys.stderr)
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)


def test_dummy_contract():
    code = """
    @external
    @view
    def foo() -> bool:
        return True
    """
    c = loads_zksync_partial(code).at("0xB27cCfd5909f46F5260Ca01BA27f591868D08704")
    assert c.foo() is True
