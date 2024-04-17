import os
import sys
from subprocess import Popen

import boa
import pytest

from boa_zksync.util import find_free_port, stop_subprocess, wait_url


@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_node = Popen(
        [
            "era_test_node",
            "--port",
            f"{era_port}",
            "fork",
            os.getenv("FORK_URL", "https://sepolia.era.zksync.dev"),
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)


def test_dummy_contract():
    code = """
@external
@view
def foo() -> bool:
    return True
    """
    c = boa.loads_partial(code).at("0xB27cCfd5909f46F5260Ca01BA27f591868D08704")
    assert c.foo() is True
