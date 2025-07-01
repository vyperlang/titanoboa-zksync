import atexit


import boa
from boa import get_verifier
from boa.verifiers import VerificationResult

from boa_zksync.contract import ZksyncContract
from boa_zksync.environment import ZksyncEnv
from boa_zksync.node import AnvilZKsync
from boa_zksync.verifiers import ZksyncExplorer

from weakref import WeakSet

# Using a WeakSet means instances are automatically removed when they are no longer
# referenced elsewhere and garbage collected.
_all_anvil_zksync_instances: WeakSet[AnvilZKsync] = WeakSet()

# Temporary tracker for the currently active AnvilZKsync node.
_original_anvil_zksync_new = AnvilZKsync.__new__


def _new_anvil_zksync_instance(cls, *args, **kwargs):
    """
    Interceptor for AnvilZKsync.__new__ to track all created instances.
    """
    import logging

    # Call the original __new__ to create the instance
    instance = _original_anvil_zksync_new(cls)
    # Add to our global tracking set
    _all_anvil_zksync_instances.add(instance)
    logging.debug(
        f"AnvilZKsync instance created and added to global tracker: {instance}"
    )
    return instance


# Replace AnvilZKsync's __new__ method with our interceptor
AnvilZKsync.__new__ = _new_anvil_zksync_instance


@atexit.register
def _stop_all_active_anvil_zksync_nodes_on_exit():
    """
    Atexit handler to stop any AnvilZKsync nodes still running when the program exits.
    This uses the global tracking set and checks for live processes.
    """
    import logging

    if not _all_anvil_zksync_instances:
        logging.debug("No AnvilZKsync instances were tracked during program execution.")
        return

    logging.info(
        "Running atexit cleanup: Checking for remaining active AnvilZKsync nodes."
    )
    nodes_to_stop = []
    # Iterate over a list copy to safely modify the WeakSet if items are removed by GC
    for node in list(_all_anvil_zksync_instances):
        # node._test_node is the Popen object. poll() returns None if still running.
        if node._test_node and node._test_node.poll() is None:
            nodes_to_stop.append(node)
        else:
            # If the process is already dead, the WeakSet will eventually remove it,
            # but we can explicitly log that it's no longer active.
            logging.debug(f"AnvilZKsync node {node} already terminated or not started.")

    if nodes_to_stop:
        logging.info(f"Stopping {len(nodes_to_stop)} remaining AnvilZKsync node(s).")
        for node in nodes_to_stop:
            try:
                # Call the original stop method
                node.stop()
                logging.info(f"Successfully stopped AnvilZKsync node: {node}")
            except Exception as e:
                logging.error(f"Error stopping AnvilZKsync node {node}: {e}")
    else:
        logging.info("No active AnvilZKsync nodes found needing cleanup at exit.")


def set_zksync_env(url, explorer_url=None, nickname=None):
    """Sets the boa environment to a zkSync network environment."""
    boa.set_verifier(ZksyncExplorer(explorer_url))
    env = ZksyncEnv.from_url(url, nickname=nickname)
    boa.set_env(env)
    return env


def set_zksync_test_env(node_args=(), nickname=None):
    """Sets the boa environment to a local Anvil ZKsync test network."""
    anvil_rpc = AnvilZKsync(node_args=node_args)
    env = ZksyncEnv(rpc=anvil_rpc, nickname=nickname)
    boa.set_env(env)
    # The AnvilZKsync instance created here will be automatically tracked.
    anvil_rpc.start()
    return env


def set_zksync_fork(url, nickname=None, *args, **kwargs):
    """
    Sets the boa environment to a forked zkSync network using a local AnvilZKsync node.
    """
    env = ZksyncEnv.from_url(url, nickname=nickname)
    # @dev The anvil_zksync_node.start() is handled within ZksyncEnv.fork_rpc
    env.fork(url=url, *args, **kwargs)
    boa.set_env(env)

    return env


def set_zksync_browser_env(*args, **kwargs):
    """Sets the boa environment to a zkSync browser environment."""
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
