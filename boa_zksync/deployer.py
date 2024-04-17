from functools import cached_property

from boa import Env
from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.rpc import to_bytes
from boa.util.abi import Address

from boa_zksync.compile import ZksyncCompilerData
from boa_zksync.environment import ZksyncEnv


class ZksyncDeployer(ABIContractFactory):
    def __init__(self, compiler_data: ZksyncCompilerData, name: str, filename: str):
        super().__init__(
            name,
            compiler_data.abi,
            functions=[
                ABIFunction(item, name)
                for item in compiler_data.abi
                if item.get("type") == "function"
            ],
            filename=filename,
        )
        self.compiler_data = compiler_data

    def deploy(self, *args, value=0, **kwargs):
        env = Env.get_singleton()
        assert isinstance(
            env, ZksyncEnv
        ), "ZksyncDeployer can only be used in zkSync environments"

        address, _ = env.deploy_code(
            bytecode=to_bytes(self.compiler_data.bytecode),
            value=value,
            constructor_calldata=(
                self.constructor.prepare_calldata(*args, **kwargs)
                if args or kwargs
                else b""
            ),
        )
        address = Address(address)
        abi_contract = ABIContract(
            self._name,
            self.abi,
            self._functions,
            address=address,
            filename=self._filename,
            env=env,
        )
        env.register_contract(address, self)
        return abi_contract

    def deploy_as_blueprint(self, *args, **kwargs):
        """
        In zkSync, any contract can be used as a blueprint.
        Note that we do need constructor arguments for this.
        """
        return self.deploy(*args, **kwargs)

    @cached_property
    def constructor(self):
        ctor_abi = next(i for i in self.abi if i["type"] == "constructor")
        return ABIFunction(ctor_abi, contract_name=self._name)
