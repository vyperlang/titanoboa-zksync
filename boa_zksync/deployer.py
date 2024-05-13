from functools import cached_property
from pathlib import Path

from boa import Env
from boa.contracts.abi.abi_contract import ABIContractFactory, ABIFunction
from boa.rpc import to_bytes
from boa.util.abi import Address

from boa_zksync.compile import compile_zksync, compile_zksync_source
from boa_zksync.contract import ZksyncContract
from boa_zksync.types import ZksyncCompilerData


class ZksyncDeployer(ABIContractFactory):

    def __init__(self, compiler_data: ZksyncCompilerData, filename=None):
        super().__init__(
            compiler_data.contract_name, compiler_data.abi, filename, compiler_data
        )

    @staticmethod
    def create_compiler_data(
        source_code: str,
        contract_name: str = None,
        filename: str = None,
        compiler_args: dict = None,
        **kwargs,
    ) -> ZksyncCompilerData:
        if not contract_name:
            contract_name = Path(filename).stem if filename else "<anonymous contract>"

        if filename:
            return compile_zksync(contract_name, filename, compiler_args)
        return compile_zksync_source(source_code, contract_name, compiler_args)

    def deploy(self, *args, value=0, **kwargs) -> ZksyncContract:
        env = Env.get_singleton()
        from boa_zksync.environment import ZksyncEnv

        assert isinstance(
            env, ZksyncEnv
        ), "ZksyncDeployer can only be used in zkSync environments"

        address, _ = env.deploy_code(
            bytecode=self.compiler_data.bytecode,
            value=value,
            constructor_calldata=(
                self.constructor.prepare_calldata(*args, **kwargs)
                if args or kwargs
                else b""
            ),
        )
        return self.at(address)

    def at(self, address: Address | str) -> ZksyncContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)
        env = Env.get_singleton()
        contract = ZksyncContract(
            self._name,
            self.abi,
            self._functions,
            address=address,
            filename=self._filename,
            env=env,
            compiler_data=self.compiler_data,
        )
        env.register_contract(address, contract)
        return contract

    def deploy_as_blueprint(self, *args, **kwargs) -> ZksyncContract:
        """
        In zkSync, any contract can be used as a blueprint.
        Note that we do need constructor arguments for this.
        """
        return self.deploy(*args, **kwargs)

    @cached_property
    def constructor(self) -> ABIFunction:
        """
        Get the constructor function of the contract.
        :raises: StopIteration if the constructor is not found.
        """
        ctor_abi = next(i for i in self.abi if i["type"] == "constructor")
        return ABIFunction(ctor_abi, contract_name=self._name)
