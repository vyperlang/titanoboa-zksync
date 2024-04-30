import logging
import os
from shutil import which

import requests
from boa.integrations.jupyter.browser import BrowserRPC, BrowserSigner, colab_eval_js
from boa.rpc import EthereumRPC

from boa_zksync.environment import ZksyncEnv


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


def install_zkvyper_compiler(
    source="https://raw.githubusercontent.com/matter-labs/zkvyper-bin/"
    "66cc159d9b6af3b5616f6ed7199bd817bf42bf0a/linux-amd64/zkvyper-linux-amd64-musl-v1.4.0",
    destination="/usr/local/bin/zkvyper",
):
    """
    Downloads the zkvyper binary from the given source URL and installs it to
    the destination directory.

    This is a very basic implementation - usually users want to install the binary
    manually, but in the Colab environment, we can automate this process.
    """
    response = requests.get(source)
    with open(destination, "wb") as f:
        f.write(response.content)

    os.chmod(destination, 0o755)  # make it executable
    assert os.system("zkvyper --version") == 0  # check if it works


def install_era_test_node(
    source="https://github.com/matter-labs/era-test-node/releases/download/"
    "v0.1.0-alpha.19/era_test_node-v0.1.0-alpha.19-x86_64-unknown-linux-gnu.tar.gz",
    destination="/usr/local/bin/era_test_node",
):
    """
    Downloads the era-test-node binary from the given source URL and installs it to
    the destination directory.

    This is a very basic implementation - usually users want to install the binary
    manually, but in the Colab environment, we can automate this process.
    """
    response = requests.get(source)
    with open("era_test_node.tar.gz", "wb") as f:
        f.write(response.content)

    os.system("tar --extract --file=era_test_node.tar.gz")
    os.system(f"mv era_test_node {destination}")
    os.system(f"{destination} --version")
    os.system("rm era_test_node.tar.gz")
