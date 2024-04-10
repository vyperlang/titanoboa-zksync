from hashlib import sha256
from pathlib import Path

import rlp
from eth_account import Account
from eth_account.messages import encode_typed_data

from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.interpret import json
from boa.network import NetworkEnv
from boa.util.abi import Address
from boa_zksync.rpc import ZksyncRPC

CONTRACT_DEPLOYER_ADDRESS = "0x0000000000000000000000000000000000008006"
with open(Path(__file__).parent / "IContractDeployer.json") as f:
    CONTRACT_DEPLOYER = ABIContractFactory.from_abi_dict(json.load(f), "ContractDeployer", )


_EIP712_TYPE = bytes.fromhex("71")
_EIP712_DOMAIN_ABI_TYPE = "EIP712Domain(string name,string version,uint256 chainId)"
_EIP712_TRANSACTION_ABI_TYPE = (
    "Transaction(uint256 txType,uint256 from,uint256 to,uint256 gasLimit,uint256 gasPerPubdataByteLimit,"
    "uint256 maxFeePerGas,uint256 maxPriorityFeePerGas,uint256 paymaster,uint256 nonce,uint256 value,"
    "bytes data,bytes32[] factoryDeps,bytes paymasterInput)"
)
_EIP712_TRANSACTION_TYPE_SPEC = {
    "Transaction": [
        { "name": "txType", "type": "uint256" },
        { "name": "from", "type": "uint256" },
        { "name": "to", "type": "uint256" },
        { "name": "gasLimit", "type": "uint256" },
        { "name": "gasPerPubdataByteLimit", "type": "uint256" },
        { "name": "maxFeePerGas", "type": "uint256" },
        { "name": "maxPriorityFeePerGas", "type": "uint256" },
        { "name": "paymaster", "type": "uint256" },
        { "name": "nonce", "type": "uint256" },
        { "name": "value", "type": "uint256" },
        { "name": "data", "type": "bytes" },
        { "name": "factoryDeps", "type": "bytes32[]" },
        { "name": "paymasterInput", "type": "bytes" }
    ]
}

class ZksyncEnv(NetworkEnv):
    def __init__(self, rpc: ZksyncRPC, accounts: dict[str, Account] = None):
        super().__init__(rpc, accounts)
        self._contract_deployer = CONTRACT_DEPLOYER.at(CONTRACT_DEPLOYER_ADDRESS)

    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b"", constructor_calldata=b"", salt=b"0" * 32, **kwargs):
        bytecode_hash = _hash_code(bytecode)
        calldata = self._contract_deployer.create.prepare_calldata(salt, bytecode_hash, constructor_calldata)

        sender = str(Address(sender or self.eoa))
        gas = gas or 0
        account = self._accounts[sender]

        nonce, chain_id = self._rpc.fetch_multi([
            ("eth_getTransactionCount", [sender, "latest"]),
            ("eth_chainId", [])
        ])

        tx_data = {
            "txType": "0x" + _EIP712_TYPE.hex(),
            "from": sender,
            "to": str(self._contract_deployer.address),
            # todo: handle gas params, maybe estimate gas
            "gasLimit": kwargs.pop("gas_limit", gas),
            "gasPerPubdataByteLimit": kwargs.pop("gas_per_pubdata_byte_limit", gas),
            "maxFeePerGas": kwargs.pop("max_fee_per_gas", gas),
            "maxPriorityFeePerGas": kwargs.pop("max_priority_fee_per_gas", gas),
            "nonce": nonce,
            "value": "0x" + value.to_bytes(32, 'big').hex(),
            "data": "0x" + calldata.hex(),
            "factoryDeps": ["0x" + bytecode_hash.hex()],
            "paymaster": 0,
            "paymasterInput": "0x",
        }

        raw_tx = _sign_message(chain_id, account, tx_data)
        tx_hash = self._rpc.fetch("eth_sendRawTransaction", ["0x" + raw_tx.hex()])
        receipt = self._rpc.wait_for_tx_receipt(tx_hash, self.tx_settings.poll_timeout)
        return receipt["contractAddress"]


def _sign_message(chain_id: str, account: Account, tx_data: dict) -> bytes:
    # https://github.com/foundry-rs/foundry/issues/4648
    return _EIP712_TYPE + rlp.encode([
        tx_data["nonce"],
        tx_data["maxPriorityFeePerGas"],
        tx_data["maxFeePerGas"],
        tx_data["gasLimit"],
        tx_data["to"],
        tx_data["value"],
        tx_data["data"],
        chain_id,
        "0x",
        "0x",
        chain_id,
        tx_data["from"],
        tx_data["gasPerPubdataByteLimit"],
        tx_data["factoryDeps"],
        _sign_typed_data(account, chain_id, tx_data),
        [tx_data["paymaster"], tx_data["paymasterInput"]]
    ])


def _sign_typed_data(account, chain_id, tx_data):
    typed_data = {
        # Based on https://github.com/zksync-sdk/zksync-ethers/blob/d31a9b1/src/signer.ts#L143
        "domain": {"name": "zkSync", "version": "2", "chainId": chain_id},
        "types": _EIP712_TRANSACTION_TYPE_SPEC,
        "message": tx_data,
    }
    if hasattr(account, "sign_typed_data"):
        return account.sign_typed_data(full_message=typed_data)

    # some providers (e.g. LocalAccount) don't have sign_typed_data
    signable_message = encode_typed_data(full_message=typed_data)
    return account.sign_message(signable_message)


def _hash_code(bytecode):
    bytecode_word_count = (len(bytecode) // 32).to_bytes(2, 'big')
    # https://docs.zksync.io/build/developer-reference/contract-deployment.html#contract-size-limit-and-format-of-bytecode-hash
    sha = sha256(bytecode).digest()
    return b"01" + bytecode_word_count + sha[:28]
