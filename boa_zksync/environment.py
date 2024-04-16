import sys
from contextlib import contextmanager
from functools import cached_property
from hashlib import sha256
from pathlib import Path
from subprocess import Popen
from typing import Any, Callable, Optional, cast

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory
from boa.environment import _AddressType
from boa.interpret import json
from boa.network import NetworkEnv, TransactionSettings, _EstimateGasFailed
from boa.rpc import RPC, fixup_dict, to_bytes, to_hex, EthereumRPC
from boa.util.abi import Address
from eth.constants import ZERO_ADDRESS
from eth.exceptions import VMError
from eth_account import Account

from boa_zksync.node import EraTestNode
from boa_zksync.util import DeployTransaction, find_free_port, wait_url, stop_subprocess

_CONTRACT_DEPLOYER_ADDRESS = "0x0000000000000000000000000000000000008006"
with open(Path(__file__).parent / "IContractDeployer.json") as f:
    CONTRACT_DEPLOYER = ABIContractFactory.from_abi_dict(
        json.load(f), "ContractDeployer"
    )


class ZksyncEnv(NetworkEnv):
    """
    An implementation of the Env class for zkSync environments.
    This is a mix-in so the logic may be reused in both network and browser modes.
    """

    def __init__(self, rpc: str | RPC, *args, **kwargs):
        super().__init__(rpc, *args, **kwargs)
        self.evm = None  # not used in zkSync

    @cached_property
    def create(self):
        return next(
            func
            for func in CONTRACT_DEPLOYER._functions
            if func.full_signature == "create(bytes32,bytes32,bytes)"
        )

    def _reset_fork(self, block_identifier="latest"):
        if isinstance(self._rpc, EraTestNode):
            url = self._rpc._inner_url
            del self._rpc
        else:
            url = self._rpc._rpc_url
        self._rpc = EthereumRPC(url)

    def fork_rpc(self, rpc: EthereumRPC, reset_traces=True, block_identifier="safe", **kwargs):
        """
        Fork the environment to a local chain.
        :param rpc: RPC to fork from
        :param reset_traces: Reset the traces
        :param block_identifier: Block identifier to fork from
        :param kwargs: Additional arguments for the RPC
        """
        self._reset_fork(block_identifier)
        if reset_traces:
            self.sha3_trace = {}
            self.sstore_trace = {}
        self._rpc = EraTestNode(rpc, block_identifier)

    def register_contract(self, address, obj):
        addr = Address(address)
        self._contracts[addr.canonical_address] = obj
        # also register it in the registry for
        # create_minimal_proxy_to and create_copy_of
        bytecode = self._rpc.fetch("eth_getCode", [address, "latest"])
        self._code_registry[bytecode] = obj

    @contextmanager
    def anchor(self):
        snapshot_id = self._rpc.fetch("evm_snapshot", [])
        yield
        self._rpc.fetch("evm_revert", [snapshot_id])

    def execute_code(
        self,
        to_address: _AddressType = ZERO_ADDRESS,
        sender: Optional[_AddressType] = None,
        gas: Optional[int] = None,
        value: int = 0,
        data: bytes = b"",
        is_modifying: bool = False,
        contract: ABIContract = None,
    ) -> Any:
        """
        Executes a contract call in the zkSync network.
        :param to_address: The address of the contract to call.
        :param sender: The address of the sender.
        :param gas: The gas limit for the transaction.
        :param value: The amount of value to send with the transaction.
        :param data: The calldata for the contract function.
        :param contract: The contract ABI.
        :return: The return value of the contract function.
        """
        sender = self._check_sender(self._get_sender(sender))

        hexdata = to_hex(data)

        if not is_modifying:
            args = fixup_dict(
                {
                    "from": sender,
                    "to": to_address,
                    "gas": gas,
                    "value": value,
                    "data": hexdata,
                }
            )
            output = self._rpc.fetch("eth_call", [args, "latest"])
            return ZksyncComputation(to_bytes(output))

        try:
            receipt, trace = self._send_txn(
                from_=sender, to=to_address, value=value, gas=gas, data=hexdata
            )
        except _EstimateGasFailed:
            return ZksyncComputation(error=VMError("Estimate gas failed"))

        return ZksyncComputation(receipt.get("output", b""))

    def deploy_code(
        self,
        sender=None,
        gas=None,
        value=0,
        bytecode=b"",
        constructor_calldata=b"",
        salt=b"\0" * 32,
        **kwargs,
    ) -> tuple[Address, bytes]:
        """
        Deploys a contract to the zkSync network.
        :param sender: The address of the sender.
        :param gas: The gas limit for the transaction.
        :param value: The amount of value to send with the transaction.
        :param bytecode: The bytecode of the contract to deploy.
        :param constructor_calldata: The calldata for the contract constructor.
        :param salt: The salt for the contract deployment.
        :param kwargs: Additional parameters for the transaction.
        :return: The address of the deployed contract and the bytecode hash.
        """
        sender = str(Address(sender or self.eoa))
        rpc_data = self._rpc.fetch_multi(
            [
                ("eth_getTransactionCount", [sender, "latest"]),
                ("eth_chainId", []),
                ("eth_gasPrice", []),
            ]
        )
        nonce, chain_id, gas_price = [int(i, 16) for i in rpc_data]

        bytecode_hash = _hash_code(bytecode)
        tx = DeployTransaction(
            sender=sender,
            to=_CONTRACT_DEPLOYER_ADDRESS,
            gas=gas or 0,
            gas_price=gas_price,
            max_priority_fee_per_gas=kwargs.pop("max_priority_fee_per_gas", gas_price),
            nonce=nonce,
            value=value,
            calldata=self.create.prepare_calldata(
                salt, bytecode_hash, constructor_calldata
            ),
            bytecode=bytecode,
            bytecode_hash=bytecode_hash,
            chain_id=chain_id,
            paymaster_params=kwargs.pop("paymaster_params", None),
        )

        estimated_gas = int(
            self._rpc.fetch("eth_estimateGas", [tx.get_estimate_tx()]), 16
        )
        signature = tx.sign_typed_data(self._accounts[sender], estimated_gas)
        raw_tx = tx.rlp_encode(signature, estimated_gas)
        tx_hash = self._rpc.fetch("eth_sendRawTransaction", ["0x" + raw_tx.hex()])
        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)
        return Address(receipt["contractAddress"]), bytecode

    def get_code(self, address):
        return self._rpc.fetch("eth_getCode", [address, "latest"])


def _hash_code(bytecode: bytes) -> bytes:
    """
    Hashes the bytecode for contract deployment, according to the zkSync spec.
    Based on https://github.com/zksync-sdk/zksync2-python/blob/d33eff9/zksync2/core/utils.py#L45
    """
    bytecode_len = len(bytecode)
    bytecode_size = int(bytecode_len / 32)
    assert bytecode_len % 32 == 0, "Bytecode length must be a multiple of 32 bytes"
    assert bytecode_size < 2**16, "Bytecode length must be less than 2^16"
    bytecode_hash = sha256(bytecode).digest()
    return b"\x01\00" + bytecode_size.to_bytes(2, byteorder="big") + bytecode_hash[4:]


class ZksyncComputation:
    def __init__(self, output: bytes | None = None, error: VMError | None = None):
        self._output = output
        self._error = error

    @property
    def is_success(self) -> bool:
        """
        Return ``True`` if the computation did not result in an error.
        """
        return self._error is None

    @property
    def is_error(self) -> bool:
        """
        Return ``True`` if the computation resulted in an error.
        """
        return self._error is not None

    @property
    def error(self) -> VMError:
        """
        Return the :class:`~eth.exceptions.VMError` of the computation.
        Raise ``AttributeError`` if no error exists.
        """
        if self._error is None:
            raise AttributeError("No error exists for this computation")
        return self._error

    def raise_if_error(self) -> None:
        """
        If there was an error during computation, raise it as an exception immediately.

        :raise VMError:
        """
        if self.is_error:
            raise self.error

    @property
    def output(self) -> bytes:
        """
        Get the return value of the computation.
        """
        if self._output is None:
            raise AttributeError("No output exists for this computation")
        return self._output
