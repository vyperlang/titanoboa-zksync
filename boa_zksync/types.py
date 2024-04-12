from dataclasses import dataclass

import rlp
from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_typed_data
from rlp.sedes import BigEndianInt, Binary, List

_EIP712_TYPE = bytes.fromhex("71")
_EIP712_TYPES_SPEC = {
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
    ]
}
_GAS_PER_PUB_DATA_DEFAULT = 50000
_BINARY = Binary()
_INT = BigEndianInt()


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
    chain_id: int
    paymaster_params: tuple[int, bytes] | None

    def get_estimate_tx(self):
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
                "factoryDeps": [[int(b) for b in self.bytecode]],
            },
        }

    def sign_typed_data(self, account: Account, estimated_gas: int) -> SignedMessage:
        """
        Creates a signature for the typed data.
        Based on https://github.com/zksync-sdk/zksync-ethers/blob/d31a9b1/src/signer.ts#L143
        """
        paymaster, paymaster_input = self.paymaster_params or (0, b"")
        domain = {"name": "zkSync", "version": "2", "chainId": self.chain_id}
        body = {
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
            "factoryDeps": [self.bytecode_hash],
            "paymaster": paymaster,
            "paymasterInput": paymaster_input,
        }
        if hasattr(account, "sign_typed_data"):
            return account.sign_typed_data(domain, _EIP712_TYPES_SPEC, body)
        encoded = encode_typed_data(domain, _EIP712_TYPES_SPEC, body)
        return account.sign_message(encoded)

    def rlp_encode(self, signature: SignedMessage, estimated_gas: int) -> bytes:
        """
        Encodes the EIP-712 transaction data to be sent to the RPC.
        Based on https://github.com/zksync-sdk/zksync2-python/blob/d33eff9/zksync2/transaction/transaction712.py#L33  # noqa
        """
        paymaster_type = List(
            elements=([_BINARY, _BINARY] if self.paymaster_params else None),
            strict=False,
        )
        return _EIP712_TYPE + rlp.encode(
            [
                _INT.serialize(self.nonce),
                _INT.serialize(self.max_priority_fee_per_gas),
                _INT.serialize(self.gas_price),
                _INT.serialize(estimated_gas),
                _BINARY.serialize(bytes.fromhex(self.to.removeprefix("0x"))),
                _INT.serialize(self.value),
                _BINARY.serialize(self.calldata),
                _INT.serialize(self.chain_id),
                _BINARY.serialize(b""),
                _BINARY.serialize(b""),
                _INT.serialize(self.chain_id),
                _BINARY.serialize(bytes.fromhex(self.sender.removeprefix("0x"))),
                _INT.serialize(_GAS_PER_PUB_DATA_DEFAULT),
                List(elements=([_BINARY]), strict=False).serialize([self.bytecode]),
                _BINARY.serialize(signature.signature),
                paymaster_type.serialize(self.paymaster_params or []),
            ]
        )
