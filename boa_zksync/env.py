from functools import cached_property
from hashlib import sha256
from pathlib import Path

from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.interpret import json
from boa.network import NetworkEnv, TransactionSettings
from boa.rpc import RPC
from boa.util.abi import Address
from eth_account import Account

from boa_zksync.types import DeployTransaction

_CONTRACT_DEPLOYER_ADDRESS = "0x0000000000000000000000000000000000008006"
with open(Path(__file__).parent / "IContractDeployer.json") as f:
    CONTRACT_DEPLOYER = ABIContractFactory.from_abi_dict(
        json.load(f), "ContractDeployer"
    )


class _ZksyncEnvMixin:
    """
    An implementation of the Env class for zkSync environments.
    This is a mix-in so the logic may be reused in both network and browser modes.
    """

    _rpc: RPC
    _accounts: dict[str, Account]
    eoa: Address
    tx_settings: TransactionSettings

    @cached_property
    def contract_deployer(self):
        return CONTRACT_DEPLOYER.at(_CONTRACT_DEPLOYER_ADDRESS)

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
            to=(str(self.contract_deployer.address)),
            gas=gas or 0,
            gas_price=gas_price,
            max_priority_fee_per_gas=kwargs.pop("max_priority_fee_per_gas", gas_price),
            nonce=nonce,
            value=value,
            calldata=self.contract_deployer.create.prepare_calldata(
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


class ZksyncEnv(_ZksyncEnvMixin, NetworkEnv):
    """
    A zkSync environment for deploying contracts using a network RPC.
    """


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
