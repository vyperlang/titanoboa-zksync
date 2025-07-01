import logging
import sys
from subprocess import Popen
from typing import Optional

from boa.rpc import EthereumRPC

from boa_zksync.util import find_free_port, is_port_free, stop_subprocess, wait_url


class AnvilZKsync(EthereumRPC):
    """Anvil ZKsync test node.

    This class starts an Anvil node with ZKsync support, allowing you to run tests
    against a local ZKsync environment. It can be used to fork a specific block
    from a ZKsync network or to run a fresh node.

    It acts as an EthereumRPC client while managing its own subprocess.

    :iparam inner_rpc: Optional EthereumRPC instance.
    :iparam block_identifier: Block number or identifier to fork from.
    :iparam node_args: Additional arguments to pass to the anvil-zksync command.
    """

    # list of public+private keys for test accounts in the anvil-zksync
    TEST_ACCOUNTS = [
        (
            "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        ),
        (
            "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
        ),
        (
            "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
            "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
        ),
        (
            "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
            "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
        ),
        (
            "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
            "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
        ),
        (
            "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
            "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
        ),
        (
            "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
            "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
        ),
        (
            "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
            "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
        ),
        (
            "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f",
            "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
        ),
        (
            "0xa0Ee7A142d267C1f36714E4a8F75612F20a79720",
            "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
        ),
    ]

    SUGGESTED_ANVIL_ZKSYNC_PORT = 8011

    def __init__(
        self,
        inner_rpc: Optional[EthereumRPC] = None,
        block_identifier="safe",
        node_args=(),
    ):
        # Set up the inner RPC URL based on the provided inner_rpc.
        self.inner_rpc = inner_rpc
        self.block_identifier = block_identifier
        self.node_args = node_args

        self._port: Optional[int] = None
        self._test_node: Optional[Popen] = None
        self._rpc_url: Optional[str] = None

        # Setup the port for the anvil-zksync node.
        # If the suggested port is free, use it; otherwise, find a free port.
        if is_port_free(self.SUGGESTED_ANVIL_ZKSYNC_PORT):
            self._port = self.SUGGESTED_ANVIL_ZKSYNC_PORT
        else:
            # If suggested port is not free, or no port provided, find a truly free one.
            self._port = find_free_port()
            logging.info(
                f"{self.SUGGESTED_ANVIL_ZKSYNC_PORT} is in use. Found free port: {self._port}"
            )

        super().__init__(f"http://localhost:{self._port}")

    def _build_command(self):
        """Build the command to run the anvil-zksync node."""
        fork_at_args = (
            ["--fork-at", f"{self.block_identifier}"]
            if isinstance(self.block_identifier, int)
            else []
        )
        command_base = (
            ["fork", "--fork-url", self.inner_rpc._rpc_url] + fork_at_args
            if self.inner_rpc
            else ["run"]
        )

        args = (
            ["anvil-zksync"]
            + list(self.node_args)
            + ["--port", f"{self._port}"]
            + command_base
        )
        return args

    def start(self):
        """Starts the anvil-zksync node."""
        if self._test_node is not None:
            logging.warning("Anvil-ZkSync node is already running. Skipping start.")
            return

        command = self._build_command()
        logging.info(f"Starting Anvil-ZkSync node with command: {' '.join(command)}")
        self._test_node = Popen(command, stdout=sys.stdout, stderr=sys.stderr)
        self._rpc_url = f"http://localhost:{self._port}"

        logging.info(f"Anvil-ZkSync node attempting to start at {self._rpc_url}")
        wait_url(self._rpc_url)
        logging.info(f"Anvil-ZkSync node running at {self._rpc_url}")

    def stop(self):
        """Stops the anvil-zksync node."""
        if self._test_node is not None:
            logging.info("Stopping Anvil-ZkSync node.")
            stop_subprocess(self._test_node)
            self._test_node = None
            self._rpc_url = None
        else:
            logging.info("Anvil-ZkSync node is not running.")

    def __del__(self):
        """Destructor to ensure the node is stopped when the instance is garbage collected."""
        if self._test_node is not None:
            logging.warning(
                "AnvilZKsync instance garbage collected without explicit stop()."
            )
            self.stop()
