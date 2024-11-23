import warnings
from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Optional

import rlp
from boa.contracts.call_trace import TraceFrame
from boa.contracts.vyper.vyper_contract import VyperDeployer
from boa.deployments import Deployment
from boa.interpret import compiler_data
from boa.rpc import fixup_dict, to_bytes, to_hex
from boa.util.abi import Address
from boa.verifiers import get_verification_bundle
from eth.exceptions import Revert, VMError
from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_typed_data
from packaging.version import Version
from rlp.sedes import BigEndianInt, Binary, List
from vyper.compiler import CompilerData
from vyper.compiler.settings import OptimizationLevel

if TYPE_CHECKING:
    from boa_zksync import ZksyncEnv
    from boa_zksync.contract import ZksyncContract


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
CONTRACT_DEPLOYER_ADDRESS = "0x0000000000000000000000000000000000008006"
DEFAULT_SALT = b"\0" * 32

_EIP712_TYPE = bytes.fromhex("71")
_EIP712_TYPES_SPEC = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "Transaction": [
        {"name": "txType", "type": "uint256"},
        {"name": "from", "type": "uint256"},
        {"name": "to", "type": "uint256"},
        {"name": "gasLimit", "type": "uint256"},
        {"name": "gasPerPubdataByteLimit", "type": "uint256"},
        {"name": "maxFeePerGas", "type": "uint256"},
        {"name": "maxPriorityFeePerGas", "type": "uint256"},
        {"name": "paymaster", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "value", "type": "uint256"},
        {"name": "data", "type": "bytes"},
        {"name": "factoryDeps", "type": "bytes32[]"},
        {"name": "paymasterInput", "type": "bytes"},
    ],
}
_GAS_PER_PUB_DATA_DEFAULT = 50000
_BINARY = Binary()
_INT = BigEndianInt()
_BIN_LIST = List(elements=([_BINARY]), strict=False)
_BIN_TUPLE_LIST = List(elements=[_BINARY, _BINARY], strict=False)
_EMPTY_LIST = List(elements=None, strict=False)


@dataclass(frozen=True)
class DeployTransaction:
    """
    Represents a transaction context for a zkSync deployment transaction.
    """

    sender: str
    to: str
    gas: int
    gas_price: int
    max_priority_fee_per_gas: int
    nonce: int
    value: int
    calldata: bytes  # the result of calling the deployer's create.prepare_calldata
    bytecode: bytes
    bytecode_hash: bytes
    dependency_bytecodes: list[bytes]
    dependency_bytecode_hashes: list[bytes]
    chain_id: int
    paymaster_params: tuple[int, bytes] | None

    def get_estimate_tx(self):
        bytecodes = [self.bytecode] + self.dependency_bytecodes
        return {
            "transactionType": f"0x{_EIP712_TYPE.hex()}",
            "chain_id": self.chain_id,
            "from": self.sender,
            "to": self.to,
            "gas": f"0x{self.gas:0x}",
            "gasPrice": f"0x{self.gas_price:0x}",
            "maxPriorityFeePerGas": f"0x{self.max_priority_fee_per_gas:0x}",
            "nonce": f"0x{self.nonce:0x}",
            "value": f"0x{self.value:0x}",
            "data": f"0x{self.calldata.hex()}",
            "eip712Meta": {
                "gasPerPubdata": f"0x{_GAS_PER_PUB_DATA_DEFAULT:0x}",
                "factoryDeps": [
                    [int(byte) for byte in bytecode] for bytecode in bytecodes
                ],
            },
        }

    def sign_typed_data(
        self, account: Account, estimated_gas: int
    ) -> SignedMessage | str:
        """
        Creates a signature for the typed data.
        Based on https://github.com/zksync-sdk/zksync-ethers/blob/d31a9b1/src/signer.ts#L143
        """
        paymaster, paymaster_input = self.paymaster_params or (0, b"")
        full_message = {
            "domain": {"name": "zkSync", "version": "2", "chainId": self.chain_id},
            "types": _EIP712_TYPES_SPEC,
            "message": {
                "txType": int(_EIP712_TYPE.hex(), 16),
                "from": self.sender,
                "to": self.to,
                "gasLimit": estimated_gas,
                "gasPerPubdataByteLimit": _GAS_PER_PUB_DATA_DEFAULT,
                "maxFeePerGas": self.max_priority_fee_per_gas,
                "maxPriorityFeePerGas": self.max_priority_fee_per_gas,
                "nonce": self.nonce,
                "value": self.value,
                "data": self.calldata,
                "factoryDeps": [self.bytecode_hash] + self.dependency_bytecode_hashes,
                "paymaster": paymaster,
                "paymasterInput": paymaster_input,
            },
            "primaryType": "Transaction",
        }
        if hasattr(account, "sign_typed_data"):
            return account.sign_typed_data(full_message=full_message)
        encoded = encode_typed_data(full_message=full_message)
        return account.sign_message(encoded)

    def rlp_encode(self, signature: SignedMessage | str, estimated_gas: int) -> bytes:
        """
        Encodes the EIP-712 transaction data to be sent to the RPC.
        Based on https://github.com/zksync-sdk/zksync2-python/blob/d33eff9/zksync2/transaction/transaction712.py#L33  # noqa
        """
        paymaster_type = _BIN_TUPLE_LIST if self.paymaster_params else _EMPTY_LIST
        bytecodes = [self.bytecode] + self.dependency_bytecodes
        return _EIP712_TYPE + rlp.encode(
            [
                _INT.serialize(self.nonce),
                _INT.serialize(self.max_priority_fee_per_gas),
                _INT.serialize(self.gas_price),
                _INT.serialize(estimated_gas),
                _BINARY.serialize(to_bytes(self.to)),
                _INT.serialize(self.value),
                _BINARY.serialize(self.calldata),
                _INT.serialize(self.chain_id),
                _BINARY.serialize(b""),
                _BINARY.serialize(b""),
                _INT.serialize(self.chain_id),
                _BINARY.serialize(to_bytes(self.sender)),
                _INT.serialize(_GAS_PER_PUB_DATA_DEFAULT),
                _BIN_LIST.serialize(bytecodes),
                _BINARY.serialize(
                    to_bytes(signature)
                    if isinstance(signature, str)
                    else signature.signature
                ),
                paymaster_type.serialize(self.paymaster_params or []),
            ]
        )

    def to_dict(self) -> dict:
        """
        Convert the DeployTransaction instance to a dictionary.
        """
        # Use asdict to convert the dataclass to a dict
        d = asdict(self)
        d["chainId"] = d.pop("chain_id")  # for consistency with boa, see #24

        # Convert bytes and list of bytes to hexadecimal strings
        for key, value in d.items():
            if isinstance(value, bytes):
                d[key] = "0x" + value.hex()
            elif isinstance(value, list) and all(
                isinstance(item, bytes) for item in value
            ):
                d[key] = ["0x" + item.hex() for item in value]

        # Handle the paymaster_params tuple specially
        if d["paymaster_params"] is not None:
            d["paymaster_params"] = {
                "paymaster": "0x" + d["paymaster_params"][0].to_bytes(20, "big").hex(),
                "paymaster_input": "0x" + d["paymaster_params"][1].hex(),
            }

        return d

    def to_deployment(
        self,
        contract: "ZksyncContract",
        receipt: dict,
        broadcast_ts: float,
        create_address: Address,
        rpc: str,
    ):
        contract_name = getattr(contract, "contract_name", None)
        if (filename := getattr(contract, "filename", None)) is not None:
            filename = str(filename) # can be Path sometimes
        try:
            source_bundle = get_verification_bundle(contract)
        except Exception as e:
            # there was a problem constructing the verification bundle.
            # assume the user cares more about continuing, than getting
            # the bundle into the db
            msg = "While saving deployment data, couldn't construct"
            msg += f" verification bundle for {contract_name}! Full stack"
            msg += f" trace:\n```\n{e}\n```\nContinuing.\n"
            warnings.warn(msg, stacklevel=2)
            source_bundle = None
        return Deployment(
            contract_address=create_address,
            contract_name=contract_name,
            filename=filename,
            rpc=rpc,
            deployer=Address(self.sender),
            tx_hash=receipt["transactionHash"],
            broadcast_ts=broadcast_ts,
            tx_dict=self.to_dict(),
            receipt_dict=receipt,
            source_code=source_bundle,
            abi=getattr(contract, "abi", None),
        )


@dataclass
class ZksyncCompilerData:
    """
    Represents the output of the Zksync Vyper compiler (combined_json format).
    """

    contract_name: str
    source_code: str
    zkvyper_version: Version
    compiler_args: list[str]
    bytecode: bytes
    method_identifiers: dict
    abi: list[dict]
    bytecode_runtime: str
    warnings: list[str]
    factory_deps: list[str]

    # zkvyper>=1.5.3 fields
    layout: Optional[dict] = None
    userdoc: Optional[dict] = None
    devdoc: Optional[dict] = None

    @cached_property
    def global_ctx(self):
        return self.vyper.global_ctx

    @cached_property
    def vyper(self) -> CompilerData:
        # TODO: Return the compile_data already created by boa.
        return compiler_data(
            self.source_code,
            self.contract_name,
            "<unknown>",
            VyperDeployer,
            optimize=OptimizationLevel.NONE,
        )


@dataclass
class ZksyncMessage:
    sender: Address
    to: Address
    gas: int
    value: int
    data: bytes

    @property
    def code_address(self) -> bytes:
        # this is used by boa to find the contract address for stack traces
        return to_bytes(self.to)

    def as_json_dict(self, sender_field="from"):
        return fixup_dict(
            {
                sender_field: self.sender,
                "to": self.to,
                "gas": self.gas,
                "value": self.value,
                "data": to_hex(self.data),
            }
        )

    def as_tx_params(self):
        return self.as_json_dict(sender_field="from_")

    @property
    def is_create(self) -> bool:
        return self.to == CONTRACT_DEPLOYER_ADDRESS


@dataclass
class ZksyncComputation:
    env: "ZksyncEnv"
    msg: ZksyncMessage
    output: bytes | None = None
    error: VMError | None = None
    children: list["ZksyncComputation"] = field(default_factory=list)
    gas_used: int = 0
    revert_reason: str | None = None
    type: str = "Call"
    value: int = 0

    @classmethod
    def from_call_trace(cls, env: "ZksyncEnv", output: dict) -> "ZksyncComputation":
        """Recursively constructs a ZksyncComputation from a debug_traceCall output."""
        error = None
        if output.get("error") is not None:
            error = VMError(output["error"])
        if output.get("revertReason") is not None:
            error = Revert(output["revertReason"])

        return cls(
            env=env,
            msg=ZksyncMessage(
                sender=Address(output["from"]),
                to=Address(output["to"]),
                gas=int(output["gas"], 16),
                value=int(output["value"], 16),
                data=to_bytes(output["input"]),
            ),
            output=to_bytes(output["output"]),
            error=error,
            children=[
                cls.from_call_trace(env, call) for call in output.get("calls", [])
            ],
            gas_used=int(output["gasUsed"], 16),
            revert_reason=output.get("revertReason"),
            type=output.get("type", "Call"),
            value=int(output.get("value", "0x"), 16),
        )

    @classmethod
    def from_debug_trace(cls, env: "ZksyncEnv", output: dict):
        """
        Finds the actual transaction computation, since zksync has system
        contract calls in the trace.
        Note: The output has more data when running via the era test node.
        """
        to, sender = output["to"], output["from"]

        def _find(calls: list[dict]):
            for trace in calls:
                if found := _find(trace["calls"]):
                    return found
                if trace["to"] == to and trace["from"] == sender:
                    return cls.from_call_trace(env, trace)

        if result := _find(output["calls"]):
            return result
        # in production mode the result is not always nested
        return cls.from_call_trace(env, output)

    @property
    def is_success(self) -> bool:
        """
        Return ``True`` if the computation did not result in an error.
        """
        return self.error is None

    @property
    def is_error(self) -> bool:
        """
        Return ``True`` if the computation resulted in an error.
        """
        return self.error is not None

    def raise_if_error(self) -> None:
        """
        If there was an error during computation, raise it as an exception immediately.

        :raise VMError:
        """
        if self.error:
            raise self.error

    def get_gas_used(self):
        return self.gas_used

    @property
    def net_gas_used(self) -> int:
        return self.get_gas_used()

    @property
    def call_trace(self) -> TraceFrame:
        return self._get_call_trace()

    def _get_call_trace(self, depth=0) -> TraceFrame:
        address = self.msg.to
        contract = self.env.lookup_contract(address)
        source = contract.trace_source(self) if contract else None
        children = [child._get_call_trace(depth + 1) for child in self.children]
        return TraceFrame(self, source, depth, children)
