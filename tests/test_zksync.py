import socket
import sys
from shutil import which
from subprocess import Popen, TimeoutExpired
from tempfile import TemporaryDirectory
from time import sleep

import boa
import pytest
import requests
from boa.contracts.abi.abi_contract import ABIContractFactory
from eth_account import Account
from requests.exceptions import ConnectionError

from boa_zksync.contract import compile_zksync, _call_zkvyper, ZksyncDeployer
from boa_zksync.env import ZksyncEnv
from boa_zksync.interpret import loads_zksync
from boa_zksync.rpc import ZksyncRPC

code = """
totalSupply: public(uint256)
balances: HashMap[address, uint256]

@external
def __init__(t: uint256):
    self.totalSupply = t
    self.balances[self] = t

@external
def update_total_supply(t: uint16):
    self.totalSupply += convert(t, uint256)

@external
def raise_exception(t: uint256):
    raise "oh no!"
"""

STARTING_SUPPLY = 100


def find_free_port():
    # https://gist.github.com/bertjwregeer/0be94ced48383a42e70c3d9fff1f4ad0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 0))
    portnum = s.getsockname()[1]
    s.close()
    return portnum


@pytest.fixture(scope="session")
def era_test_node():
    era_port = find_free_port()
    era_cmd = f"era_test_node --port {era_port} run".split(" ")
    era_node = Popen(era_cmd, stdout=sys.stdout, stderr=sys.stderr)
    yield wait_url(f"http://localhost:{era_port}")
    stop_subprocess(era_node)


def wait_url(url: str):
    while True:
        try:
            requests.head(url)
            return url
        except ConnectionError:
            sleep(0.1)


def stop_subprocess(proc: Popen[bytes]):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


@pytest.fixture(scope="module")
def account():
    return Account.from_key("0x3d3cbc973389cb26f657686445bcc75662b415b656078503592ac8c1abb8810e")


@pytest.fixture(scope="module", autouse=True)
def zksync_env(era_test_node, account):
    env = ZksyncEnv(ZksyncRPC(era_test_node))
    env.add_account(account)
    with boa.swap_env(env):
        yield


@pytest.fixture(scope="module")
def simple_contract():
    return loads_zksync(code, STARTING_SUPPLY)


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY


def test_deploy_via_sdk(era_test_node, account):
    from eth_account.signers.local import LocalAccount
    from eth_typing import HexAddress
    from zksync2.core.types import EthBlockParams
    from zksync2.manage_contracts.contract_encoder_base import ContractEncoder
    from zksync2.module.module_builder import ZkSyncBuilder
    from zksync2.signer.eth_signer import PrivateKeyEthSigner
    from zksync2.transaction.transaction_builders import TxCreateContract

    def deploy_contract(zk_web3: ZkSyncBuilder, account: LocalAccount, abi, bytecode, calldata) -> HexAddress:
        """Deploy compiled contract on zkSync network using create() opcode

        :param zk_web3:
            Instance of ZkSyncBuilder that interacts with zkSync network

        :param account:
            From which account the deployment contract tx will be made

        :compiled_contract:
            Compiled contract source.

        :return:
            Address of deployed contract.

        """
        # Get chain id of zkSync network
        chain_id = zk_web3.zksync.chain_id

        # Signer is used to generate signature of provided transaction
        signer = PrivateKeyEthSigner(account, chain_id)

        # Get nonce of ETH address on zkSync network
        nonce = zk_web3.zksync.get_transaction_count(account.address, EthBlockParams.PENDING.value)

        # Get contract ABI and bytecode information
        counter_contract = ContractEncoder(zk_web3, abi, bytecode)

        # Get current gas price in Wei
        gas_price = zk_web3.zksync.gas_price

        # Create deployment contract transaction
        create_contract = TxCreateContract(web3=zk_web3,
                                           chain_id=chain_id,
                                           nonce=nonce,
                                           from_=account.address,
                                           gas_limit=0,  # UNKNOWN AT THIS STATE
                                           gas_price=gas_price,
                                           bytecode=counter_contract.bytecode,
                                           max_priority_fee_per_gas=gas_price,
                                           call_data=calldata
                                          )

        # ZkSync transaction gas estimation
        estimate_gas = zk_web3.zksync.eth_estimate_gas(create_contract.tx)
        print(f"Fee for transaction is: {estimate_gas * gas_price}")

        # Convert transaction to EIP-712 format
        tx_712 = create_contract.tx712(estimate_gas)

        # Sign message
        typed_data = tx_712.to_eip712_struct()
        signed_message = signer.sign_typed_data(typed_data)

        # Encode signed message
        msg = tx_712.encode(signed_message)

        # Deploy contract
        tx_hash = zk_web3.zksync.send_raw_transaction(msg)

        # Wait for deployment contract transaction to be included in a block
        tx_receipt = zk_web3.zksync.wait_for_transaction_receipt(tx_hash, timeout=240, poll_latency=0.5)

        print(f"Tx status: {tx_receipt['status']}")
        contract_address = tx_receipt["contractAddress"]

        print(f"Deployed contract address: {contract_address}")

        # Return the contract deployed address
        return contract_address

    # Connect to zkSync network
    zk_web3 = ZkSyncBuilder.build(era_test_node)

    # Provide a compiled JSON source contract
    with TemporaryDirectory() as tempdir:
        with open(f"{tempdir}/test.vy", "w") as in_file:
            in_file.write(code)

        compiled = compile_zksync(in_file.name)
        deployer = ZksyncDeployer(compiled, "SimpleContract", in_file.name)
        calldata = deployer.constructor.prepare_calldata(STARTING_SUPPLY)
        # Perform contract deployment
        address = deploy_contract(zk_web3, account, compiled.abi, compiled.bytecode, calldata)

    simple_contract = deployer.at(address)
    assert simple_contract.totalSupply() == STARTING_SUPPLY
