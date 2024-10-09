import json
import subprocess
from os import path
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory

from boa.rpc import to_bytes

from boa_zksync.compiler_utils import get_compiler_output
from boa_zksync.types import ZksyncCompilerData


def compile_zksync(
    contract_name: str, filename: str, compiler_args=None, source_code=None
) -> ZksyncCompilerData:
    vyper_path = which("vyper")
    assert vyper_path, "Vyper executable not found"
    compiler_args = compiler_args or []
    compile_result = subprocess.run(
        [
            "zkvyper",
            # make sure zkvyper uses the same vyper as boa
            "--vyper",
            vyper_path,
            # request JSON output
            "-f",
            "combined_json",
            # pass any extra compiler args
            *compiler_args,
            # pass the file name
            "--",
            filename,
        ],
        capture_output=True,
    )

    assert compile_result.returncode == 0, compile_result.stderr.decode()
    output = json.loads(compile_result.stdout.decode())
    if source_code is None:
        with open(filename) as file:
            source_code = file.read()

    compile_output = get_compiler_output(output)
    bytecode = to_bytes(compile_output.pop("bytecode"))
    return ZksyncCompilerData(
        contract_name, source_code, compiler_args, bytecode, **compile_output
    )


def compile_zksync_source(
    source_code: str, name: str, compiler_args=None
) -> ZksyncCompilerData:
    """
    Compile a contract from source code.
    :param source_code: The source code of the contract.
    :param name: The (file)name of the contract. If this is a file name, the
        contract name will be the file name without the extension.
    :param compiler_args: Extra arguments to pass to the compiler.
    :return: The compiled contract.
    """
    if path.exists(name):
        # We need to accept filenames because of the way `boa.load` works
        contract_name = Path(name).stem
        return compile_zksync(contract_name, name, compiler_args, source_code)

    with TemporaryDirectory() as tempdir:
        filename = f"{tempdir}/{name}.vy"
        with open(filename, "w") as file:
            file.write(source_code)
        return compile_zksync(name, filename, compiler_args, source_code)
