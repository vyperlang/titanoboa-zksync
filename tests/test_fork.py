import os
import sys
from subprocess import Popen

import boa
import pytest

from boa_zksync.util import find_free_port, stop_subprocess, wait_url


def test_dummy_contract(zksync_fork_env):
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
