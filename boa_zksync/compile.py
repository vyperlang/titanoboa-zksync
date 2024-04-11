import json
import subprocess
from collections import namedtuple
from shutil import which

ZksyncCompilerData = namedtuple(
    "ZksyncCompilerData",
    [
        "method_identifiers",
        "abi",
        "bytecode",
        "bytecode_runtime",
        "warnings",
        "factory_deps",
    ],
)


def compile_zksync(file_name: str, compiler_args=None) -> ZksyncCompilerData:
    output = json.loads(
        _call_zkvyper(
            # make sure zkvyper uses the same vyper as boa
            "--vyper",
            which("vyper"),
            # request JSON output
            "-f",
            "combined_json",
            # pass any extra compiler args
            *(compiler_args or []),
            # pass the file name
            "--",
            file_name,
        )
    )
    return ZksyncCompilerData(**output[file_name])


def _call_zkvyper(*args):
    result = subprocess.run(["zkvyper", *args], capture_output=True)
    if result.returncode == 0:
        return result.stdout.decode()
    raise Exception(result.stderr.decode())
