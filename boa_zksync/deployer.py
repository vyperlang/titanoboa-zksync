from functools import cached_property

from boa import Env
from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.rpc import to_bytes
from boa.util.abi import Address

from boa_zksync.compile import ZksyncCompilerData


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

        initcode = to_bytes(self.compiler_data.bytecode)
        constructor_calldata = (
            self.constructor.prepare_calldata(*args, **kwargs)
            if args or kwargs
            else b""
        )

        address, _ = env.deploy_code(
            bytecode=initcode, value=value, constructor_calldata=constructor_calldata
        )
        return ABIContract(
            self._name,
            self.abi,
            self._functions,
            address=Address(address),
            filename=self._filename,
            env=env,
        )

    @cached_property
    def constructor(self):
        ctor_abi = next(i for i in self.abi if i["type"] == "constructor")
        return ABIFunction(ctor_abi, contract_name=self._name)
