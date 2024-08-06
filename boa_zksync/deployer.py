from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from boa import Env
from boa.contracts.abi.abi_contract import ABIContractFactory, ABIFunction
from boa.util.abi import Address
from vyper.compiler import CompilerData

from boa_zksync.compile import compile_zksync, compile_zksync_source
from boa_zksync.contract import ZksyncContract
from boa_zksync.types import ZksyncCompilerData

if TYPE_CHECKING:
    from boa_zksync.environment import ZksyncEnv


class ZksyncDeployer(ABIContractFactory):

    def __init__(self, compiler_data: CompilerData, filename=None):
        contract_name = Path(compiler_data.contract_path).stem
        self.zkvyper_data = self._compile(compiler_data, contract_name, filename)
        super().__init__(
            contract_name, self.zkvyper_data.abi, compiler_data.contract_path
        )

    @staticmethod
    def _compile(
        compiler_data: CompilerData,
        contract_name: str,
        filename: str,
        compiler_args: dict = None,
    ) -> ZksyncCompilerData:
        if filename in ("", None, "<unknown>"):
            return compile_zksync_source(
                compiler_data.file_input.source_code, contract_name, compiler_args
            )
        return compile_zksync(contract_name, filename, compiler_args)

    @classmethod
    def from_abi_dict(cls, abi, name="<anonymous contract>", filename=None):
        raise NotImplementedError("ZksyncDeployer does not support loading from ABI")

    def deploy(self, *args, value=0, **kwargs) -> ZksyncContract:
        address, _ = self.env.deploy_code(
            bytecode=self.zkvyper_data.bytecode,
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
        contract = ZksyncContract(
            self.zkvyper_data,
            self._name,
            self.abi,
            self.functions,
            address=address,
            filename=self.filename,
            env=self.env,
        )
        self.env.register_contract(address, contract)
        return contract

    def deploy_as_blueprint(self, *args, **kwargs) -> ZksyncContract:
        """
        In zkSync, any contract can be used as a blueprint.
        Note that we do need constructor arguments for deploying a blueprint.
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

    @property
    def env(self) -> "ZksyncEnv":
        """
        Get the environment for this deployer. Ensures that the environment is a ZksyncEnv.
        :return: The ZksyncEnv singleton.
        """
        env = Env.get_singleton()
        from boa_zksync.environment import ZksyncEnv

        assert isinstance(
            env, ZksyncEnv
        ), "ZksyncDeployer can only be used in zkSync environments"
        return env
