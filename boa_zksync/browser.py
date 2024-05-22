import logging
from shutil import which

from boa.integrations.jupyter.browser import BrowserRPC, BrowserSigner, colab_eval_js
from boa.rpc import EthereumRPC

from boa_zksync.environment import ZksyncEnv
from boa_zksync.util import install_era_test_node, install_zkvyper_compiler


class ZksyncBrowserEnv(ZksyncEnv):
    """
    A zkSync environment for deploying contracts using a browser wallet RPC.
    """

    def __init__(self, address=None, *args, **kwargs):
        if colab_eval_js and not which("zkvyper"):
            logging.warning(
                "Automatically installing zkvyper compiler in the Colab environment."
            )
            install_zkvyper_compiler()

        super().__init__(BrowserRPC(), *args, **kwargs)
        self.signer = BrowserSigner(address)
        self.set_eoa(self.signer)

    def set_chain_id(self, chain_id: int | str):
        self._rpc.fetch(
            "wallet_switchEthereumChain",
            [{"chainId": chain_id if isinstance(chain_id, str) else hex(chain_id)}],
        )
        self._reset_fork()

    def fork_rpc(
        self, rpc: EthereumRPC, reset_traces=True, block_identifier="safe", **kwargs
    ):
        if colab_eval_js and not which("era_test_node"):
            logging.warning(
                "Automatically installing era-test-node in the Colab environment."
            )
            install_era_test_node()

        return super().fork_rpc(rpc, reset_traces, block_identifier, **kwargs)
