import json
import subprocess
from shutil import which
from tempfile import TemporaryDirectory

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
    return ZksyncCompilerData(
        contract_name, source_code, compiler_args, **output[filename]
    )


def compile_zksync_source(
    source_code: str, name: str, compiler_args=None
) -> ZksyncCompilerData:
    with TemporaryDirectory() as tempdir:
        filename = f"{tempdir}/{name}.vy"
        with open(filename, "w") as file:
            file.write(source_code)
        return compile_zksync(name, filename, compiler_args, source_code)
