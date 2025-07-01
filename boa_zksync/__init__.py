import atexit
from typing import Optional

import boa
from boa import get_verifier
from boa.verifiers import VerificationResult

from boa_zksync.contract import ZksyncContract
from boa_zksync.environment import ZksyncEnv
from boa_zksync.node import AnvilZKsync
from boa_zksync.verifiers import ZksyncExplorer

# Module-level variable to track the currently active AnvilZKsync node
_current_anvil_zksync_node: Optional[AnvilZKsync] = None


@atexit.register
def _stop_active_anvil_zksync_node():
    """Helper function to stop the currently tracked AnvilZKsync node.

    This function is registered to run at exit, ensuring that any active
    AnvilZKsync node is stopped cleanly when the program exits.
    """
    import logging

    global _current_anvil_zksync_node
    if _current_anvil_zksync_node is not None:
        logging.info("Stopping active AnvilZKsync node via boa_zksync global cleanup.")
        _current_anvil_zksync_node.stop()
        _current_anvil_zksync_node = None
    else:
        logging.debug("No active AnvilZKsync node to stop.")


def set_zksync_env(url, explorer_url=None, nickname=None):
    """Sets the boa environment to a zkSync network environment."""
    boa.set_verifier(ZksyncExplorer(explorer_url))
    env = ZksyncEnv.from_url(url, nickname=nickname)
    boa.set_env(env)

    # Ensure any previously active AnvilZKsync is stopped
    _stop_active_anvil_zksync_node()
    return env


def set_zksync_test_env(node_args=(), nickname=None):
    """
    Sets the boa environment to a local Anvil ZKsync test network.
    Manages the AnvilZKsync subprocess lifecycle.
    """
    global _current_anvil_zksync_node

    # Stop any previously active AnvilZKsync node before starting a new one
    _stop_active_anvil_zksync_node()

    anvil_rpc = AnvilZKsync(node_args=node_args)
    env = ZksyncEnv(rpc=anvil_rpc, nickname=nickname)
    boa.set_env(env)

    # Start the new AnvilZKsync node and track it
    anvil_rpc.start()
    _current_anvil_zksync_node = anvil_rpc

    return env


def set_zksync_fork(url, nickname=None, *args, **kwargs):
    """
    Sets the boa environment to a forked zkSync network using a local AnvilZKsync node.
    Manages the AnvilZKsync subprocess lifecycle.
    """
    global _current_anvil_zksync_node

    # Stop any previously active AnvilZKsync node before starting a new one
    _stop_active_anvil_zksync_node()

    env = ZksyncEnv.from_url(url, nickname=nickname)
    # The fork() method internally creates an AnvilZKsync instance and sets it as env._rpc
    env.fork(*args, **kwargs)
    boa.set_env(env)

    # Start the AnvilZKsync node created by fork() and track it
    if isinstance(env._rpc, AnvilZKsync):
        env._rpc.start()
        _current_anvil_zksync_node = env._rpc
    else:
        # This case implies a non-AnvilZKsync RPC was used for forking,
        # so ensure no AnvilZKsync is tracked.
        _current_anvil_zksync_node = None

    return env


def set_zksync_browser_env(*args, **kwargs):
    """Sets the boa environment to a zkSync browser environment."""
    # Ensure any previously active AnvilZKsync is stopped
    _stop_active_anvil_zksync_node()

    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv

    env = ZksyncBrowserEnv(*args, **kwargs)
    boa.set_env(env)
    return env


boa.set_zksync_env = set_zksync_env
boa.set_zksync_test_env = set_zksync_test_env
boa.set_zksync_fork = set_zksync_fork
boa.set_zksync_browser_env = set_zksync_browser_env


def verify(contract: ZksyncContract, verifier=None, **kwargs) -> VerificationResult:
    verifier = verifier or get_verifier()
    return verifier.verify(
        address=contract.address,
        solc_json=contract.deployer.solc_json,
        contract_name=contract.contract_name,
        constructor_calldata=contract.constructor_calldata,
        **kwargs,
    )
