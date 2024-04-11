from functools import cached_property

from boa.interpret import json
import subprocess
from collections import namedtuple
from shutil import which
from typing import Optional

from boa import Env
from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory, ABIFunction
from boa.util.abi import Address, abi_encode

_ZKVYPER_BIN_REPOSITORY = 'https://github.com/matter-labs/zkvyper-bin'
_zkvyper_path: str | None = None
_vyper_path = which("vyper") or which("vyper.exe")
ZksyncCompilerData = namedtuple("ZksyncCompilerData", [
    'method_identifiers', 'abi', 'bytecode', 'bytecode_runtime', 'warnings', 'factory_deps',
])


class ZksyncContract(ABIContract):
    def __init__(
        self,
        name: str,
        abi: dict,
        functions: list[ABIFunction],
        address: Address,
        filename: Optional[str] = None,
        env=None,
    ):
        super().__init__(name, abi, functions, address, filename, env)


class ZksyncDeployer(ABIContractFactory):
    def __init__(self, compiler_data: ZksyncCompilerData, name: str, filename: str):
        super().__init__(
            name,
            compiler_data.abi,
            functions=[
                ABIFunction(item, name) for item in compiler_data.abi
                if item.get("type") == "function"
            ],
            filename=filename,
        )
        self.compiler_data = compiler_data

    def deploy(self, *args, value=0, **kwargs):
        env = Env.get_singleton()

        initcode = bytes.fromhex(self.compiler_data.bytecode.removeprefix("0x"))
        constructor_calldata = self.constructor.prepare_calldata(*args, **kwargs) if args or kwargs else b""

        address, _ = env.deploy_code(bytecode=initcode, value=value, constructor_calldata=constructor_calldata)
        return ZksyncContract(
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


def compile_zksync(file_name: str, compiler_args = None) -> ZksyncCompilerData:
    output = json.loads(_call_zkvyper(
        # make sure zkvyper uses the same vyper as boa
        "--vyper", which("vyper"),
        # request JSON output
        "-f", "combined_json",
        # pass any extra compiler args
        *(compiler_args or []),
        # pass the file name
        "--", file_name,
    ))
    return ZksyncCompilerData(**output[file_name])


def _call_zkvyper(*args):
    result = subprocess.run(["zkvyper", *args], capture_output=True)
    if result.returncode == 0:
        return result.stdout.decode()
    raise Exception(result.stderr.decode())
