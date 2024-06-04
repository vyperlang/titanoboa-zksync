import logging
import sys
from subprocess import Popen
from typing import Optional

from boa.rpc import EthereumRPC

from boa_zksync.util import find_free_port, stop_subprocess, wait_url


class EraTestNode(EthereumRPC):
    # list of public+private keys for test accounts in the era_test_node
    TEST_ACCOUNTS = [
        (
            "0xBC989fDe9e54cAd2aB4392Af6dF60f04873A033A",
            "0x3d3cbc973389cb26f657686445bcc75662b415b656078503592ac8c1abb8810e",
        ),
        (
            "0x55bE1B079b53962746B2e86d12f158a41DF294A6",
            "0x509ca2e9e6acf0ba086477910950125e698d4ea70fa6f63e000c5a22bda9361c",
        ),
        (
            "0xCE9e6063674DC585F6F3c7eaBe82B9936143Ba6C",
            "0x71781d3a358e7a65150e894264ccc594993fbc0ea12d69508a340bc1d4f5bfbc",
        ),
        (
            "0xd986b0cB0D1Ad4CCCF0C4947554003fC0Be548E9",
            "0x379d31d4a7031ead87397f332aab69ef5cd843ba3898249ca1046633c0c7eefe",
        ),
        (
            "0x87d6ab9fE5Adef46228fB490810f0F5CB16D6d04",
            "0x105de4e75fe465d075e1daae5647a02e3aad54b8d23cf1f70ba382b9f9bee839",
        ),
        (
            "0x78cAD996530109838eb016619f5931a03250489A",
            "0x7becc4a46e0c3b512d380ca73a4c868f790d1055a7698f38fb3ca2b2ac97efbb",
        ),
        (
            "0xc981b213603171963F81C687B9fC880d33CaeD16",
            "0xe0415469c10f3b1142ce0262497fe5c7a0795f0cbfd466a6bfa31968d0f70841",
        ),
        (
            "0x42F3dc38Da81e984B92A95CBdAAA5fA2bd5cb1Ba",
            "0x4d91647d0a8429ac4433c83254fb9625332693c848e578062fe96362f32bfe91",
        ),
        (
            "0x64F47EeD3dC749d13e49291d46Ea8378755fB6DF",
            "0x41c9f9518aa07b50cb1c0cc160d45547f57638dd824a8d85b5eb3bf99ed2bdeb",
        ),
        (
            "0xe2b8Cb53a43a56d4d2AB6131C81Bd76B86D3AFe5",
            "0xb0680d66303a0163a19294f1ef8c95cd69a9d7902a4aca99c05f3e134e68a11a",
        ),
    ]

    def __init__(
        self,
        inner_rpc: Optional[EthereumRPC] = None,
        block_identifier="safe",
        node_args=(),
    ):
        self.inner_rpc = inner_rpc

        port = find_free_port()
        fork_at = (
            ["--fork-at", f"{block_identifier}"]
            if isinstance(block_identifier, int)
            else []
        )
        command = ["fork", inner_rpc._rpc_url] + fork_at if inner_rpc else ["run"]
        args = ["era_test_node"] + list(node_args) + ["--port", f"{port}"] + command
        self._test_node = Popen(args, stdout=sys.stdout, stderr=sys.stderr)

        super().__init__(f"http://localhost:{port}")
        logging.info(f"Started fork node at {self._rpc_url}")
        wait_url(self._rpc_url)

    def __del__(self):
        stop_subprocess(self._test_node)
