import json
import subprocess
from dataclasses import dataclass
from shutil import which


@dataclass
class ZksyncCompilerData:
    """
    Represents the output of the Zksync Vyper compiler (combined_json format).
    """

    method_identifiers: dict
    abi: list
    bytecode: str
    bytecode_runtime: str
    warnings: list
    factory_deps: list


def compile_zksync(file_name: str, compiler_args=None) -> ZksyncCompilerData:
    vyper_path = which("vyper")
    assert vyper_path, "Vyper executable not found"
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
            *(compiler_args or []),
            # pass the file name
            "--",
            file_name,
        ],
        capture_output=True,
    )

    assert compile_result.returncode == 0, compile_result.stderr.decode()
    output = json.loads(compile_result.stdout.decode())
    return ZksyncCompilerData(**output[file_name])
