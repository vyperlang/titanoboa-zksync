import logging
import textwrap
from tempfile import TemporaryDirectory

from boa.contracts.abi.abi_contract import ABIContract

from boa_zksync.compile import compile_zksync
from boa_zksync.deployer import ZksyncDeployer


def load_zksync(filename: str, *args, compiler_args=None, **kwargs) -> ABIContract:
    deployer = load_zksync_partial(filename, filename, compiler_args)
    return deployer.deploy(*args, **kwargs)


def loads_zksync(source_code, *args, name=None, compiler_args=None, **kwargs):
    d = loads_zksync_partial(source_code, name, compiler_args=compiler_args)
    return d.deploy(*args, **kwargs)


def loads_zksync_partial(
    source_code: str, name: str = None, dedent: bool = True, compiler_args: dict = None
) -> ZksyncDeployer:
    name = name or "VyperContract"  # TODO handle this upstream in CompilerData
    if dedent:
        source_code = textwrap.dedent(source_code)

    compiler_args = compiler_args or {}

    with TemporaryDirectory() as tempdir:
        with open(f"{tempdir}/{name}.vy", "w") as file:
            file.write(source_code)

        return load_zksync_partial(file.name, name, compiler_args)


def eval_zksync(code):
    return loads_zksync("").eval(code)


def load_zksync_partial(filename: str, name=None, compiler_args=None) -> ZksyncDeployer:
    compiler_data = compile_zksync(filename, compiler_args=compiler_args)
    if not compiler_data.abi:
        logging.warning("No ABI found in compiled contract")
    return ZksyncDeployer(compiler_data, name or filename, filename=filename)


__all__ = []  # type: ignore
