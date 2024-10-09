from typing import Any

import boa
import pytest
from _pytest.monkeypatch import MonkeyPatch

from boa_zksync import set_zksync_browser_env
from boa_zksync.environment import ZERO_ADDRESS


def _javascript_call(js_func: str, *args, timeout_message: str) -> Any:
    if js_func == "rpc":
        method = args[0]
        if method == "evm_snapshot":
            return 1

        if method == "eth_requestAccounts":
            return [ZERO_ADDRESS]

        if method == "evm_revert":
            assert args[1:] == ([1],), f"Bad args passed to mock: {args}"
            return None

        if method == "wallet_switchEthereumChain":
            assert args[1:] == (
                [{"chainId": "0x1"}],
            ), f"Bad args passed to mock: {args}"
            return None

        raise KeyError(args)

    if js_func == "loadSigner":
        return ZERO_ADDRESS

    raise KeyError(js_func)


@pytest.fixture(scope="session", autouse=True)
def patch_js():
    # we call MonkeyPatch directly because the default `monkeypatch` fixture has a function scope
    # this clashes with the boa plugin that tries to clean up the env after each test.
    patch = MonkeyPatch()
    patch.setattr("boa.integrations.jupyter.browser._javascript_call", _javascript_call)
    yield
    patch.undo()


@pytest.fixture
def browser_env():
    set_zksync_browser_env()


def test_browser(browser_env):
    boa.env.set_chain_id(1)
