from hashlib import sha256
from pathlib import Path

import rlp
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.interpret import json
from boa.network import NetworkEnv
from boa.util.abi import Address
from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_typed_data
from rlp.sedes import BigEndianInt, Binary, List

from boa_zksync.rpc import ZksyncRPC

_CONTRACT_DEPLOYER_ADDRESS = "0x0000000000000000000000000000000000008006"
with open(Path(__file__).parent / "IContractDeployer.json") as f:
    CONTRACT_DEPLOYER = ABIContractFactory.from_abi_dict(
        json.load(f), "ContractDeployer"
    )

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


class ZksyncEnv(NetworkEnv):
    def __init__(self, rpc: ZksyncRPC, accounts: dict[str, Account] = None):
        super().__init__(rpc, accounts)
        self.contract_deployer = CONTRACT_DEPLOYER.at(_CONTRACT_DEPLOYER_ADDRESS)

    def deploy_code(
        self,
        sender=None,
        gas=None,
        value=0,
        bytecode=b"",
        constructor_calldata=b"",
        salt=b"\0" * 32,
        **kwargs,
    ):
        bytecode_hash = _hash_code(bytecode)
        calldata = self.contract_deployer.create.prepare_calldata(
            salt, bytecode_hash, constructor_calldata
        )

        sender = str(Address(sender or self.eoa))
        gas = gas or 0  # unknown at this state
        account = self._accounts[sender]

        nonce, chain_id, gas_price = [
            int(i, 16)
            for i in self._rpc.fetch_multi(
                [
                    ("eth_getTransactionCount", [sender, "latest"]),
                    ("eth_chainId", []),
                    ("eth_gasPrice", []),
                ]
            )
        ]

        max_priority_fee_per_gas = kwargs.pop("max_priority_fee_per_gas", gas_price)
        to = str(self.contract_deployer.address)
        tx_data = {
            "transactionType": f"0x{_EIP712_TYPE.hex()}",
            "chain_id": chain_id,
            "from": sender,
            "to": to,
            "gas": f"0x{gas:0x}",
            "gasPrice": f"0x{gas_price:0x}",
            "maxPriorityFeePerGas": f"0x{max_priority_fee_per_gas :0x}",
            "nonce": f"0x{nonce:0x}",
            "value": f"0x{value:0x}",
            "data": f"0x{calldata.hex()}",
            "eip712Meta": {
                "gasPerPubdata": f"0x{_GAS_PER_PUB_DATA_DEFAULT:0x}",
                "factoryDeps": [[int(b) for b in bytecode]],
            },
        }

        estimated_gas = int(self._rpc.fetch("eth_estimateGas", [tx_data]), 16)
        paymaster_params = kwargs.pop("paymaster_params", None)
        signature = _sign_typed_data(
            account,
            sender,
            value,
            bytecode_hash,
            calldata,
            to,
            nonce,
            max_priority_fee_per_gas,
            chain_id,
            paymaster_params,
            estimated_gas,
        )
        raw_tx = _rlp_encode(
            sender,
            value,
            bytecode,
            calldata,
            to,
            nonce,
            max_priority_fee_per_gas,
            gas_price,
            chain_id,
            paymaster_params,
            signature,
            estimated_gas,
        )
        tx_hash = self._rpc.fetch("eth_sendRawTransaction", ["0x" + raw_tx.hex()])
        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)
        return receipt["contractAddress"], receipt.get("output")


def _rlp_encode(
    sender: str,
    value: int,
    bytecode: bytes,
    data: bytes,
    to: str,
    nonce: int,
    max_priority_fee_per_gas: int,
    gas_price: int,
    chain_id: int,
    paymaster_params: tuple[int, bytes] | None,
    signature: SignedMessage,
    estimated_gas: int,
) -> bytes:
    """
    Encodes the EIP-712 transaction data to be sent to the RPC.
    Based on https://github.com/zksync-sdk/zksync2-python/blob/d33eff9/zksync2/transaction/transaction712.py#L33  # noqa
    """
    return _EIP712_TYPE + rlp.encode(
        [
            _INT.serialize(nonce),
            _INT.serialize(max_priority_fee_per_gas),
            _INT.serialize(gas_price),
            _INT.serialize(estimated_gas),
            _BINARY.serialize(bytes.fromhex(to.removeprefix("0x"))),
            _INT.serialize(value),
            _BINARY.serialize(data),
            _INT.serialize(chain_id),
            _BINARY.serialize(b""),
            _BINARY.serialize(b""),
            _INT.serialize(chain_id),
            _BINARY.serialize(bytes.fromhex(sender.removeprefix("0x"))),
            _INT.serialize(_GAS_PER_PUB_DATA_DEFAULT),
            List(elements=([_BINARY]), strict=False).serialize([bytecode]),
            _BINARY.serialize(signature.signature),
            List(
                elements=([_BINARY, _BINARY] if paymaster_params else None),
                strict=False,
            ).serialize(paymaster_params or []),
        ]
    )


def _sign_typed_data(
    account: Account,
    sender: str,
    value: int,
    bytecode_hash: bytes,
    data: bytes,
    to: str,
    nonce: int,
    max_priority_fee_per_gas: int,
    chain_id: int,
    paymaster_params: tuple[int, bytes] | None,
    estimated_gas: int,
) -> SignedMessage:
    """
    Creates a signature for the typed data.
    Based on https://github.com/zksync-sdk/zksync-ethers/blob/d31a9b1/src/signer.ts#L143
    """
    paymaster, paymaster_input = paymaster_params or (0, b"")
    typed_data = {
        "domain": {"name": "zkSync", "version": "2", "chainId": chain_id},
        "types": _EIP712_TYPES_SPEC,
        "message": {
            "txType": int(_EIP712_TYPE.hex(), 16),
            "from": sender,
            "to": to,
            "gasLimit": estimated_gas,
            "gasPerPubdataByteLimit": _GAS_PER_PUB_DATA_DEFAULT,
            "maxFeePerGas": max_priority_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas,
            "nonce": nonce,
            "value": value,
            "data": data,
            "factoryDeps": [bytecode_hash],
            "paymaster": paymaster,
            "paymasterInput": paymaster_input,
        },
    }
    if hasattr(account, "sign_typed_data"):
        return account.sign_typed_data(full_message=typed_data)

    encoded = encode_typed_data(full_message=typed_data)
    return account.sign_message(encoded)


def _hash_code(bytecode: bytes) -> bytes:
    """Hashes the bytecode to be deployed."""
    bytecode_len = len(bytecode)
    bytecode_size = int(bytecode_len / 32)
    assert bytecode_len % 32 == 0, "Bytecode length must be a multiple of 32 bytes"
    assert bytecode_size < 2**16, "Bytecode length must be less than 2^16"
    bytecode_hash = sha256(bytecode).digest()
    return b"\x01\00" + bytecode_size.to_bytes(2, byteorder="big") + bytecode_hash[4:]
