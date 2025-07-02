import boa
from boa import get_verifier
from boa.verifiers import VerificationResult

from boa_zksync.contract import ZksyncContract
from boa_zksync.environment import ZksyncEnv
from boa_zksync.node import AnvilZKsync
from boa_zksync.verifiers import ZksyncExplorer


def set_zksync_env(url, explorer_url=None, nickname=None):
    """Sets the boa environment to a zkSync network environment."""
    boa.set_verifier(ZksyncExplorer(explorer_url))
    env = ZksyncEnv.from_url(url, nickname=nickname)
    return boa.set_env(env)


def set_zksync_test_env(node_args=(), nickname=None):
    """Sets the boa environment to a local Anvil ZKsync test network."""
    anvil_rpc = AnvilZKsync(node_args=node_args)
    env = ZksyncEnv(rpc=anvil_rpc, nickname=nickname)
    # The AnvilZKsync instance created here will be automatically tracked.
    anvil_rpc.start()
    return boa.set_env(env)


def set_zksync_fork(url, nickname=None, *args, **kwargs):
    """
    Sets the boa environment to a forked zkSync network using a local AnvilZKsync node.
    """
    env = ZksyncEnv.from_url(url, nickname=nickname)
    # @dev The anvil_zksync_node.start() is handled within ZksyncEnv.fork_rpc
    env.fork(url=url, *args, **kwargs)
    return boa.set_env(env)


def set_zksync_browser_env(*args, **kwargs):
    """Sets the boa environment to a zkSync browser environment."""
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv

    env = ZksyncBrowserEnv(*args, **kwargs)
    return boa.set_env(env)


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
