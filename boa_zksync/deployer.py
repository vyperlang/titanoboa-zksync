from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from boa import Env
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.util.abi import Address
from vyper.compiler import CompilerData
from vyper.compiler.output import build_solc_json

from boa_zksync.compile import compile_zksync, compile_zksync_source
from boa_zksync.contract import ZksyncBlueprint, ZksyncContract
from boa_zksync.types import ZksyncCompilerData

if TYPE_CHECKING:
    from boa_zksync.environment import ZksyncEnv


class ZksyncDeployer(ABIContractFactory):
    def __init__(self, compiler_data: CompilerData, filename=None, zkvyper_data=None):
        contract_name = Path(compiler_data.contract_path).stem
        if zkvyper_data is None:
            zkvyper_data = self._compile(compiler_data, contract_name, filename)
        self.zkvyper_data = zkvyper_data
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

    def deploy(
        self, *args, contract_name: Optional[str] = None, **kwargs
    ) -> ZksyncContract:
        return ZksyncContract(
            self.zkvyper_data,
            contract_name or self._name,
            self.functions,
            *args,
            filename=self.filename,
            **kwargs,
        )

    def at(self, address: Address | str) -> ZksyncContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        return self.deploy(override_address=Address(address), skip_initcode=True)

    def deploy_as_blueprint(
        self, contract_name: Optional[str] = None, **kwargs
    ) -> ZksyncContract:
        """
        In zkSync, any contract can be used as a blueprint.
        The only difference here is that we don't need to run the constructor.
        """
        return ZksyncBlueprint(
            self.zkvyper_data,
            contract_name or self._name,
            self.functions,
            filename=self.filename,
            **kwargs,
        )

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

    @cached_property
    def solc_json(self) -> dict:
        """
        A ZKsync compatible solc-json. Generates a solc "standard json" representation
        of the Vyper contract.
        """
        return {
            "zkvyper_version": self.zkvyper_data.zkvyper_version,
            **build_solc_json(self.zkvyper_data.vyper),
        }
