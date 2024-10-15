import time
from contextlib import contextmanager
from functools import cached_property
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Optional, Type

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory
from boa.deployments import get_deployments_db
from boa.environment import _AddressType
from boa.interpret import json
from boa.network import NetworkEnv, _EstimateGasFailed
from boa.rpc import RPC, EthereumRPC, RPCError, to_hex, to_int
from boa.util.abi import Address
from eth.exceptions import VMError
from eth_account import Account
from requests import HTTPError

from boa_zksync.deployer import ZksyncDeployer
from boa_zksync.node import EraTestNode
from boa_zksync.types import (
    CONTRACT_DEPLOYER_ADDRESS,
    DEFAULT_SALT,
    ZERO_ADDRESS,
    DeployTransaction,
    ZksyncComputation,
    ZksyncMessage,
)

with open(Path(__file__).parent / "IContractDeployer.json") as f:
    CONTRACT_DEPLOYER = ABIContractFactory.from_abi_dict(
        json.load(f), "ContractDeployer"
    )


class ZksyncEnv(NetworkEnv):
    """
    An implementation of the Env class for zkSync environments.
    This is a mix-in so the logic may be reused in both network and browser modes.
    """

    deployer_class = ZksyncDeployer

    def __init__(self, rpc: str | RPC, *args, **kwargs):
        super().__init__(rpc, *args, **kwargs)
        self.evm = None  # not used in zkSync
        self.last_receipt: dict | None = None
        self._vm = None

    @cached_property
    def create(self):
        return next(
            func
            for func in CONTRACT_DEPLOYER.functions
            if func.full_signature == "create(bytes32,bytes32,bytes)"
        )

    @property
    def vm(self):
        if self._vm is None:
            self._vm = lambda: None
            self._vm.state = _RPCState(self._rpc)
        return self._vm

    def _reset_fork(self, block_identifier="latest"):
        self._vm = None
        if (
            block_identifier == "latest"
            and isinstance(self._rpc, EraTestNode)
            and (inner_rpc := self._rpc.inner_rpc)
        ):
            del self._rpc  # close the old rpc
            self._rpc = inner_rpc

    def fork(
        self, url: str = None, reset_traces=True, block_identifier="safe", **kwargs
    ):
        if url:
            return super().fork(url, reset_traces, block_identifier, **kwargs)
        return self.fork_rpc(self._rpc, reset_traces, block_identifier, **kwargs)

    def fork_rpc(
        self, rpc: EthereumRPC, reset_traces=True, block_identifier="safe", **kwargs
    ):
        """
        Fork the environment to a local chain.
        :param rpc: RPC to fork from
        :param reset_traces: Reset the traces
        :param block_identifier: Block identifier to fork from
        :param kwargs: Additional arguments for the RPC
        """
        self._reset_fork(block_identifier)
        if reset_traces:
            self.sha3_trace: dict = {}
            self.sstore_trace: dict = {}
        self._rpc = EraTestNode(rpc, block_identifier, **kwargs)

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
        override_bytecode: bytes = None,
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
        args = ZksyncMessage(sender, to_address, gas or 0, value, data)

        try:
            trace_call = self._rpc.fetch(
                "debug_traceCall",
                [args.as_json_dict(), "latest", {"tracer": "callTracer"}],
            )
            traced_computation = ZksyncComputation.from_call_trace(self, trace_call)
        except (RPCError, HTTPError):
            output = self._rpc.fetch("eth_call", [args.as_json_dict(), "latest"])
            traced_computation = ZksyncComputation(
                self, args, bytes.fromhex(output.removeprefix("0x"))
            )

        if is_modifying:
            try:
                tx_data, receipt, trace = self._send_txn(**args.as_tx_params())
                self.last_receipt = receipt
                if trace:
                    assert (
                        traced_computation.is_error == trace.is_error
                    ), f"VMError mismatch: {traced_computation.error} != {trace.error}"
                    return ZksyncComputation.from_debug_trace(self, trace.raw_trace)

            except _EstimateGasFailed:
                if not traced_computation.is_error:  # trace gives more information
                    return ZksyncComputation(
                        self, args, error=VMError("Estimate gas failed")
                    )

        return traced_computation

    def deploy(self, *args, **kwargs):
        raise NotImplementedError("Please use `deploy_code` instead")

    def deploy_code(
        self,
        sender=None,
        gas=None,
        value=0,
        bytecode=b"",
        constructor_calldata=b"",
        dependency_bytecodes: Iterable[bytes] = (),
        salt=DEFAULT_SALT,
        max_priority_fee_per_gas=None,
        contract=None,
        **kwargs,
    ) -> tuple[Address, bytes]:
        """
        Deploys a contract to the zkSync network.
        :param sender: The address of the sender.
        :param gas: The gas limit for the transaction.
        :param value: The amount of value to send with the transaction.
        :param bytecode: The bytecode of the contract to deploy.
        :param constructor_calldata: The calldata for the contract constructor.
        :param dependency_bytecodes: The bytecodes of the blueprints.
        :param salt: The salt for the contract deployment.
        :param max_priority_fee_per_gas: The max priority fee per gas for the transaction.
        :param contract: The ZksyncContract that is being deployed.
        :param kwargs: Additional parameters for the transaction.
        :return: The address of the deployed contract and the bytecode hash.
        """
        sender = self._check_sender(self._get_sender(sender))
        if sender not in self._accounts:
            tip = (
                f"Known accounts: {list(self._accounts)}"
                if self._accounts
                else "Did you forget to call `add_account`?"
            )
            raise ValueError(f"Account {sender} is not available. ${tip}")

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
            to=CONTRACT_DEPLOYER_ADDRESS,
            gas=gas or 0,
            gas_price=gas_price,
            max_priority_fee_per_gas=max_priority_fee_per_gas or gas_price,
            nonce=nonce,
            value=value,
            calldata=self.create.prepare_calldata(
                salt, bytecode_hash, constructor_calldata
            ),
            bytecode=bytecode,
            bytecode_hash=bytecode_hash,
            dependency_bytecodes=list(dependency_bytecodes),
            dependency_bytecode_hashes=[_hash_code(bc) for bc in dependency_bytecodes],
            chain_id=chain_id,
            paymaster_params=kwargs.pop("paymaster_params", None),
        )

        estimated_gas = self._rpc.fetch("eth_estimateGas", [tx.get_estimate_tx()])
        estimated_gas = int(estimated_gas, 16)

        signature = tx.sign_typed_data(self._accounts[sender], estimated_gas)
        raw_tx = tx.rlp_encode(signature, estimated_gas)

        broadcast_ts = time.time()

        # Why do we do this over using _send_txn?
        tx_hash = self._rpc.fetch("eth_sendRawTransaction", ["0x" + raw_tx.hex()])
        print(f"tx broadcasted: {tx_hash}")
        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)
        self.last_receipt = receipt

        print(f"{tx_hash} mined in block {receipt['blockHash']}!")

        create_address = Address(receipt["contractAddress"])

        print(f"Contract deployed at {create_address}")

        if (deployments_db := get_deployments_db()) is not None:
            deployment_data = tx.to_deployment(
                contract, receipt, broadcast_ts, create_address, self._rpc.name
            )
            deployments_db.insert_deployment(deployment_data)

        return create_address, bytecode

    def get_code(self, address: Address) -> bytes:
        return self._rpc.fetch("eth_getCode", [address, "latest"])

    def set_code(self, address: Address, bytecode: bytes):
        return self._rpc.fetch("hardhat_setCode", [address, f"0x{bytecode.hex()}"])

    def generate_address(self, alias: Optional[str] = None) -> _AddressType:
        """
        Generates a new address for the zkSync environment.
        This is different from in the base env as we need the private key to
        sign transactions later.
        :param alias: An alias for the address.
        :return: The address.
        """
        if not hasattr(self, "_accounts"):
            return None  # todo: this is called during initialization
        account = Account.create(alias or f"account-{len(self._accounts)}")
        self.add_account(account)

        address = Address(account.address)
        if alias:
            self._aliases[alias] = address
        return address

    def get_balance(self, addr: Address):
        balance = self._rpc.fetch("eth_getBalance", [addr, "latest"])
        return to_int(balance)

    def set_balance(self, addr: Address, value: int):
        self._rpc.fetch("hardhat_setBalance", [addr, to_hex(value)])

    # Override
    @classmethod
    def from_url(cls, url: str, nickname=None) -> "NetworkEnv":
        return cls(EthereumRPC(url), nickname=nickname)


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


class _RPCProperty:
    def __init__(self, getter, setter):
        self.getter = getter
        self.setter = setter

    def __set_name__(
        self, owner: Type["_RPCState"], name: str
    ) -> None: ...  # python descriptor protocol

    def __get__(self, state: "_RPCState", owner):
        if state is None:
            return self  # static call
        return self.getter(state.rpc)

    def __set__(self, state: "_RPCState", value):
        self.setter(state.rpc, value)


class _RPCState:
    # Test node adds a virtual empty block at the end of the batch.
    # When you use the RPC - you get the timestamp of the last actually committed block.
    timestamp = _RPCProperty(
        lambda rpc: to_int(
            rpc.fetch_uncached("eth_getBlockByNumber", ["pending", False])["timestamp"]
        )
        + 1,
        lambda rpc, value: rpc.fetch_uncached("evm_setTime", [value - 1]),
    )

    def __init__(self, rpc):
        self.rpc = rpc
