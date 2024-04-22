import json
import subprocess
from shutil import which
from tempfile import TemporaryDirectory

from boa_zksync.types import ZksyncCompilerData


def compile_zksync(filename: str, compiler_args=None) -> ZksyncCompilerData:
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
            filename,
        ],
        capture_output=True,
    )

    assert compile_result.returncode == 0, compile_result.stderr.decode()
    output = json.loads(compile_result.stdout.decode())
    return ZksyncCompilerData(**output[filename])


def compile_zksync_source(
    source_code: str, name: str, compiler_args=None
) -> ZksyncCompilerData:
    with TemporaryDirectory() as tempdir:
        filename = f"{tempdir}/{name}.vy"
        with open(filename, "w") as file:
            file.write(source_code)
        return compile_zksync(filename, compiler_args)
