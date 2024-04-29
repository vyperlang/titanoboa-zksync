from contextlib import contextmanager
from functools import cached_property
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Optional

from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory
from boa.environment import _AddressType
from boa.interpret import json
from boa.network import NetworkEnv, _EstimateGasFailed
from boa.rpc import RPC, EthereumRPC, to_hex
from boa.util.abi import Address
from eth.exceptions import VMError
from eth_account import Account

from boa_zksync.compile import compile_zksync, compile_zksync_source
from boa_zksync.deployer import ZksyncDeployer
from boa_zksync.node import EraTestNode
from boa_zksync.types import DeployTransaction, ZksyncComputation, ZksyncMessage

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
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

    _DEFAULT_BALANCE = 10**20

    def __init__(self, rpc: str | RPC, *args, **kwargs):
        super().__init__(rpc, *args, **kwargs)
        self.evm = None  # not used in zkSync
        self.eoa = self.generate_address("eoa")

    @cached_property
    def create(self):
        return next(
            func
            for func in CONTRACT_DEPLOYER._functions
            if func.full_signature == "create(bytes32,bytes32,bytes)"
        )

    def _reset_fork(self, block_identifier="latest"):
        if isinstance(self._rpc, EraTestNode) and (inner_rpc := self._rpc.inner_rpc):
            del self._rpc
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

        trace_call = self._rpc.fetch("debug_traceCall", [args.as_json_dict(), "latest"])
        traced_computation = ZksyncComputation.from_trace(trace_call)
        if is_modifying:
            try:
                receipt, trace = self._send_txn(**args.as_tx_params())
                assert (
                    traced_computation.is_error == trace.is_error
                ), f"VMError mismatch: {traced_computation.error} != {trace.error}"
            except _EstimateGasFailed:
                if not traced_computation.is_error:  # trace gives more information
                    return ZksyncComputation(args, error=VMError("Estimate gas failed"))

        return traced_computation

    def deploy_code(
        self,
        sender=None,
        gas=None,
        value=0,
        bytecode=b"",
        constructor_calldata=b"",
        dependency_bytecodes: Iterable[bytes] = (),
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
        :param dependency_bytecodes: The bytecodes of the blueprints.
        :param salt: The salt for the contract deployment.
        :param kwargs: Additional parameters for the transaction.
        :return: The address of the deployed contract and the bytecode hash.
        """
        sender = self._check_sender(self._get_sender(sender))
        if sender not in self._accounts:
            raise ValueError(f"Account {sender} is not available.")

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
            dependency_bytecodes=list(dependency_bytecodes),
            dependency_bytecode_hashes=[_hash_code(bc) for bc in dependency_bytecodes],
            chain_id=chain_id,
            paymaster_params=kwargs.pop("paymaster_params", None),
        )

        estimated_gas = self._rpc.fetch("eth_estimateGas", [tx.get_estimate_tx()])
        estimated_gas = int(estimated_gas, 16)

        signature = tx.sign_typed_data(self._accounts[sender], estimated_gas)
        raw_tx = tx.rlp_encode(signature, estimated_gas)

        tx_hash = self._rpc.fetch("eth_sendRawTransaction", ["0x" + raw_tx.hex()])
        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)
        return Address(receipt["contractAddress"]), bytecode

    def get_code(self, address: Address) -> bytes:
        return self._rpc.fetch("eth_getCode", [address, "latest"])

    def set_code(self, address: Address, bytecode: bytes):
        return self._rpc.fetch("hardhat_setCode", [address, list(bytecode)])

    def create_deployer(
        self,
        source_code: str,
        name: str = None,
        filename: str = None,
        dedent: bool = True,
        compiler_args: dict = None,
    ) -> "ZksyncDeployer":
        if not name:
            name = Path(filename).stem if filename else "<anonymous contract>"

        if filename:
            compiler_data = compile_zksync(name, filename, compiler_args)
        else:
            compiler_data = compile_zksync_source(source_code, name, compiler_args)

        return ZksyncDeployer.from_abi_dict(
            compiler_data.abi, name, filename, compiler_data
        )

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
        self.set_balance(address, self._DEFAULT_BALANCE)
        if alias:
            self._aliases[alias] = address
        return address

    def get_balance(self, addr: Address):
        return self._rpc.fetch("eth_getBalance", [addr, "latest"])

    def set_balance(self, addr: Address, value: int):
        self._rpc.fetch("hardhat_setBalance", [addr, to_hex(value)])


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
