import boa
from boa import get_verifier
from boa.verifiers import VerificationResult

from boa_zksync.contract import ZksyncContract
from boa_zksync.environment import ZksyncEnv
from boa_zksync.node import EraTestNode
from boa_zksync.verifiers import ZksyncExplorer


def set_zksync_env(url, explorer_url=None, nickname=None):
    boa.set_verifier(ZksyncExplorer(explorer_url))
    return boa.set_env(ZksyncEnv.from_url(url, nickname=nickname))


def set_zksync_test_env(node_args=(), nickname=None):
    return boa.set_env(
        ZksyncEnv(rpc=EraTestNode(node_args=node_args), nickname=nickname)
    )


def set_zksync_fork(url, nickname=None, *args, **kwargs):
    env = ZksyncEnv.from_url(url, nickname=nickname)
    env.fork(*args, **kwargs)
    return boa.set_env(env)


def set_zksync_browser_env(*args, **kwargs):
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv

    return boa.set_env(ZksyncBrowserEnv(*args, **kwargs))


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
