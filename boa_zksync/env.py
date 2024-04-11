from hashlib import sha256
from pathlib import Path

import rlp
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.interpret import json
from boa.network import NetworkEnv
from boa.util.abi import Address, abi_encode
from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_defunct
from rlp.sedes import Binary, BigEndianInt, List
from vyper.utils import keccak256

from boa_zksync.rpc import ZksyncRPC

CONTRACT_DEPLOYER_ADDRESS = "0x0000000000000000000000000000000000008006"
with open(Path(__file__).parent / "IContractDeployer.json") as f:
    CONTRACT_DEPLOYER = ABIContractFactory.from_abi_dict(json.load(f), "ContractDeployer", )

_EIP712_TYPE = bytes.fromhex("71")
_EIP712_DOMAIN_ABI_TYPE = "EIP712Domain(string name,string version,uint256 chainId)"
_EIP712_DOMAIN_ABI_TYPE_SPEC = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"}
]
_EIP712_TRANSACTION_ABI_TYPE = (
    "Transaction(uint256 txType,uint256 from,uint256 to,uint256 gasLimit,uint256 "
    "gasPerPubdataByteLimit,uint256 maxFeePerGas,uint256 maxPriorityFeePerGas,"
    "uint256 paymaster,uint256 nonce,uint256 value,bytes data,bytes32[] factoryDeps,"
    "bytes paymasterInput)"
)
_EIP712_TRANSACTION_SPEC = [
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
    {"name": "paymasterInput", "type": "bytes"}
]
_EIP712_TYPES_SPEC = {"Transaction": _EIP712_TRANSACTION_SPEC}
_GAS_PER_PUB_DATA_DEFAULT = 50000


class ZksyncEnv(NetworkEnv):
    def __init__(self, rpc: ZksyncRPC, accounts: dict[str, Account] = None):
        super().__init__(rpc, accounts)
        self.contract_deployer = CONTRACT_DEPLOYER.at(CONTRACT_DEPLOYER_ADDRESS)

    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b"", constructor_calldata=b"", salt=b"\0" * 32,
                    **kwargs):
        bytecode_hash = _hash_code(bytecode)
        calldata = self.contract_deployer.create.prepare_calldata(salt, bytecode_hash, constructor_calldata)

        sender = str(Address(sender or self.eoa))
        gas = gas or 0  # unknown at this state
        account = self._accounts[sender]

        nonce, chain_id, gas_price = self._rpc.fetch_multi([
            ("eth_getTransactionCount", [sender, "latest"]),
            ("eth_chainId", []),
            ("eth_gasPrice", [])
        ])
        chain_id = int(chain_id, 16)
        gas_price = int(gas_price, 16)

        tx_data = {
            "transactionType": f"0x{_EIP712_TYPE.hex()}",
            "chain_id": chain_id,
            "from": sender,
            "to": str(self.contract_deployer.address),
            "gas": f"0x{gas:0x}",
            "gasPrice": f"0x{gas_price:0x}",
            "maxPriorityFeePerGas": f"0x{kwargs.pop('max_priority_fee_per_gas', gas_price):0x}",
            "nonce": nonce,
            "value": f"0x{value:0x}",
            "data": f"0x{calldata.hex()}",
            "eip712Meta": {
                "gasPerPubdata": f"0x{_GAS_PER_PUB_DATA_DEFAULT:0x}",
                "factoryDeps": [[int(b) for b in bytecode]],
            }
        }

        estimated_gas = self._rpc.fetch("eth_estimateGas", [tx_data])
        signature = _sign_typed_data(account, estimated_gas, tx_data)
        raw_tx = _encode_msg(tx_data, signature, estimated_gas)
        tx_hash = self._rpc.fetch("eth_sendRawTransaction", ["0x" + raw_tx.hex()])
        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)
        return receipt["contractAddress"], receipt.get("output")


def _encode_msg(tx_data: dict, signature: SignedMessage, estimated_gas: str) -> bytes:
    binary = Binary()
    big_endian_int = BigEndianInt()

    factory_deps_data = []
    factory_deps_elements = None
    factory_deps = tx_data["eip712Meta"]["factoryDeps"]
    if factory_deps is not None and len(factory_deps) > 0:
        factory_deps_data = [bytes(b) for b in factory_deps]
        factory_deps_elements = [binary for _ in range(len(factory_deps_data))]

    paymaster_params_data = []
    paymaster_params_elements = None
    paymaster_params = tx_data["eip712Meta"].get("paymaster")
    if (
        paymaster_params is not None
        and paymaster_params.paymaster is not None
        and paymaster_params.paymaster_input is not None
    ):
        paymaster_params_data = [
            bytes.fromhex(paymaster_params["paymaster"].removeprefix("0x")),
            paymaster_params["paymaster_input"],
        ]
        paymaster_params_elements = [binary, binary]

    class InternalRepresentation(rlp.Serializable):
        fields = [
            ("nonce", big_endian_int),
            ("maxPriorityFeePerGas", big_endian_int),
            ("maxFeePerGas", big_endian_int),
            ("gasLimit", big_endian_int),
            ("to", binary),
            ("value", big_endian_int),
            ("data", binary),
            ("chain_id", big_endian_int),
            ("unknown1", binary),
            ("unknown2", binary),
            ("chain_id2", big_endian_int),
            ("from", binary),
            ("gasPerPubdata", big_endian_int),
            ("factoryDeps", List(elements=factory_deps_elements, strict=False)),
            ("signature", binary),
            (
                "paymaster_params",
                List(elements=paymaster_params_elements, strict=False),
            ),
        ]

    representation_params = {
        "nonce": int(tx_data["nonce"], 16),
        "maxPriorityFeePerGas": int(tx_data["maxPriorityFeePerGas"], 16),
        "maxFeePerGas": int(tx_data["gasPrice"], 16),
        "gasLimit": int(estimated_gas, 16),
        "to": bytes.fromhex(tx_data["to"].removeprefix("0x")),
        "value": int(tx_data["value"], 16),
        "data": bytes.fromhex(tx_data["data"].removeprefix("0x")),
        "chain_id": tx_data["chain_id"],
        "unknown1": b"",
        "unknown2": b"",
        "chain_id2": tx_data["chain_id"],
        "from": bytes.fromhex(tx_data["from"].removeprefix("0x")),
        "gasPerPubdata": int(tx_data["eip712Meta"]["gasPerPubdata"], 16),
        "factoryDeps": factory_deps_data,
        "signature": signature.signature,
        "paymaster_params": paymaster_params_data,
    }

    representation = InternalRepresentation(**representation_params)
    encoded_rlp = rlp.encode(representation, infer_serializer=True, cache=False)
    return _EIP712_TYPE + encoded_rlp


def _sign_typed_data(account, estimated_gas, tx_data) -> SignedMessage:
    typed_data = {
        # Based on https://github.com/zksync-sdk/zksync-ethers/blob/d31a9b1/src/signer.ts#L143
        "domain": {"name": "zkSync", "version": "2", "chainId": tx_data["chain_id"]},
        "types": _EIP712_TYPES_SPEC,
        "message": {
            "txType": int(_EIP712_TYPE.hex(), 16),
            "from": int(tx_data["from"], 16),
            "to": int(tx_data["to"], 16),
            "gasLimit": int(estimated_gas, 16),
            "gasPerPubdataByteLimit": int(tx_data["eip712Meta"]["gasPerPubdata"], 16),
            "maxFeePerGas": int(tx_data["maxPriorityFeePerGas"], 16),
            "maxPriorityFeePerGas": int(tx_data["maxPriorityFeePerGas"], 16),
            "nonce": int(tx_data["nonce"], 16),
            "value": int(tx_data["value"], 16),
            "data": bytes.fromhex(tx_data["data"].removeprefix("0x")),
            "factoryDeps": [
                _hash_code(bytes(dep)) for dep in tx_data["eip712Meta"]["factoryDeps"]
            ],
            "paymaster": 0,
            "paymasterInput": b"",
        }
    }
    if hasattr(account, "sign_typed_data"):
        return account.sign_typed_data(full_message=typed_data)

    # some providers (e.g. LocalAccount) don't have sign_typed_data
    encoded_domain = _encode_struct(_EIP712_DOMAIN_ABI_TYPE_SPEC, typed_data["domain"])
    encoded_body = _encode_struct(_EIP712_TRANSACTION_SPEC, typed_data["message"])
    msg = [
        b"\x19\x01",
        keccak256(keccak256(_EIP712_DOMAIN_ABI_TYPE.encode()) + b"".join(encoded_domain)),
        keccak256(keccak256(_EIP712_TRANSACTION_ABI_TYPE.encode()) + b"".join(encoded_body))
    ]
    singable_message = encode_defunct(b"".join(msg))
    msg_hash = keccak256(singable_message.body)
    return account.signHash(msg_hash)


def _encode_struct(spec: list[dict], data: dict):
    return [_encode_data(data[field["name"]], field["type"]) for field in spec]


def _encode_data(data, typ):
    match typ:
        case "string":
            return keccak256(data.encode())
        case "bytes":
            return keccak256(data)
        case "bytes32[]":
            return keccak256(b"".join([b for b in data]))
        case _:
            return abi_encode(typ, data)


def _hash_code(bytecode: bytes) -> bytes:
    bytecode_len = len(bytecode)
    bytecode_size = int(bytecode_len / 32)
    if bytecode_len % 32 != 0:
        raise RuntimeError("Bytecode length in 32-byte words must be odd")
    if bytecode_size > 2 ** 16:
        raise OverflowError("hash_byte_code, bytecode length must be less than 2^16")
    bytecode_hash = sha256(bytecode).digest()
    encoded_len = bytecode_size.to_bytes(2, byteorder="big")
    ret = b"\x01\00" + encoded_len + bytecode_hash[4:]
    return ret
