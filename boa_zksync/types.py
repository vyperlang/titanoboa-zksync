from dataclasses import dataclass, field
from functools import cached_property
from typing import Optional

import rlp
from boa.contracts.vyper.vyper_contract import VyperDeployer
from boa.interpret import compiler_data
from boa.rpc import fixup_dict, to_bytes, to_hex
from boa.util.abi import Address
from eth.exceptions import Revert, VMError
from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_typed_data
from rlp.sedes import BigEndianInt, Binary, List
from vyper.compiler import CompilerData, Settings
from vyper.compiler.settings import OptimizationLevel

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
            "maxPriorityFeePerGas": f"0x{self.max_priority_fee_per_gas :0x}",
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


@dataclass
class ZksyncCompilerData:
    """
    Represents the output of the Zksync Vyper compiler (combined_json format).
    """

    contract_name: str
    source_code: str
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
        return compiler_data(
            self.source_code, self.contract_name, VyperDeployer, settings=self.settings
        )

    @cached_property
    def settings(self):
        return Settings(optimize=OptimizationLevel.NONE)


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


@dataclass
class ZksyncComputation:
    msg: ZksyncMessage
    output: bytes | None = None
    error: VMError | None = None
    children: list["ZksyncComputation"] = field(default_factory=list)
    gas_used: int = 0
    revert_reason: str | None = None
    type: str = "Call"
    value: int = 0

    @classmethod
    def from_call_trace(cls, output: dict) -> "ZksyncComputation":
        """Recursively constructs a ZksyncComputation from a debug_traceCall output."""
        error = None
        if output.get("error") is not None:
            error = VMError(output["error"])
        if output.get("revertReason") is not None:
            error = Revert(output["revertReason"])

        return cls(
            msg=ZksyncMessage(
                sender=Address(output["from"]),
                to=Address(output["to"]),
                gas=int(output["gas"], 16),
                value=int(output["value"], 16),
                data=to_bytes(output["input"]),
            ),
            output=to_bytes(output["output"]),
            error=error,
            children=[cls.from_call_trace(call) for call in output.get("calls", [])],
            gas_used=int(output["gasUsed"], 16),
            revert_reason=output.get("revertReason"),
            type=output.get("type", "Call"),
            value=int(output.get("value", "0x"), 16),
        )

    @classmethod
    def from_debug_trace(cls, output: dict):
        """
        Finds the actual transaction computation, since zksync has system
        contract calls in the trace.
        """
        to, sender = output["to"], output["from"]

        def _find(calls: list[dict]):
            for trace in calls:
                if found := _find(trace["calls"]):
                    return found
                if trace["to"] == to and trace["from"] == sender:
                    return cls.from_call_trace(trace)

        return _find(output["calls"])

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
