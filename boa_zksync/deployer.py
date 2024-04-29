from functools import cached_property

from boa import Env
from boa.contracts.abi.abi_contract import ABIContractFactory, ABIFunction
from boa.rpc import to_bytes
from boa.util.abi import Address

from boa_zksync.contract import ZksyncContract


class ZksyncDeployer(ABIContractFactory):
    def deploy(self, *args, value=0, **kwargs) -> ZksyncContract:
        env = Env.get_singleton()
        from boa_zksync.environment import ZksyncEnv

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
        return self.at(address)

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
