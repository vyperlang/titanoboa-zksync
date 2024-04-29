import logging
import sys
from subprocess import Popen
from typing import Optional

from boa.rpc import EthereumRPC

from boa_zksync.util import find_free_port, stop_subprocess, wait_url


class EraTestNode(EthereumRPC):
    def __init__(self, rpc: Optional[EthereumRPC] = None, block_identifier="safe"):
        self.inner_rpc = rpc

        port = find_free_port()
        fork_at = (
            ["--fork-at", block_identifier] if isinstance(block_identifier, int) else []
        )
        fork_args = ["--fork", rpc._rpc_url] + fork_at if rpc else ["run"]
        self._test_node = Popen(
            ["era_test_node", "--port", f"{port}"] + fork_args,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        super().__init__(f"http://localhost:{port}")
        logging.info(f"Started fork node at {self._rpc_url}")
        wait_url(self._rpc_url)

    def __del__(self):
        stop_subprocess(self._test_node)
