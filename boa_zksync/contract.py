import textwrap
from contextlib import contextmanager
from unittest.mock import MagicMock

from boa.contracts.abi.abi_contract import ABIContract, ABIFunction
from boa.contracts.vyper.compiler_utils import (
    generate_source_for_internal_fn,
    generate_source_for_arbitrary_stmt,
    detect_statement_type,
)
from boa.contracts.vyper.vyper_contract import VyperContract
from boa.rpc import to_bytes
from cached_property import cached_property
from vyper.semantics.analysis.base import VarInfo
from vyper.semantics.types.function import ContractFunctionT

from boa_zksync.compile import compile_zksync_source


class ZksyncContract(ABIContract):
    """
    A contract deployed to the Zksync network.
    """

    def eval(self, code):
        return ZksyncEval(code, self)()

    @contextmanager
    def override_vyper_namespace(self):
        c = VyperContract(self.compiler_data.vyper, env=self.env, override_address=self.address, skip_initcode=True, filename=self.filename)
        with c.override_vyper_namespace():
            yield

    @cached_property
    def _storage(self):
        def storage(): return None
        for name, var in self.compiler_data.global_ctx.variables.items():
            if not var.is_immutable and not var.is_constant:
                setattr(storage, name, ZksyncInternalVariable(var, name, self))
        return storage

    @cached_property
    def internal(self):
        def internal(): return None
        for fn in self.compiler_data.global_ctx.functions:
            typ = fn._metadata["type"]
            if typ.is_internal:
                setattr(internal, fn.name, ZksyncInternalFunction(typ, self))
        return internal


class _ZksyncInternal(ABIFunction):
    """
    An ABI function that temporarily changes the bytecode at the contract's address.
    """

    @cached_property
    def _override_bytecode(self):
        data = self.contract.compiler_data
        source = "\n".join((data.source_code, self.source_code))
        compiled = compile_zksync_source(source, self.name, data.compiler_args)
        return to_bytes(compiled.bytecode)

    @property
    def source_code(self):
        raise NotImplementedError  # to be implemented in subclasses

    def __call__(self, *args, **kwargs):
        env = self.contract.env
        env.set_code(self.contract.address, self._override_bytecode)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            env.set_code(self.contract.address, to_bytes(self.contract._bytecode))


class ZksyncInternalFunction(_ZksyncInternal):
    def __init__(self, fn: ContractFunctionT, contract: ZksyncContract):
        abi = {
            "anonymous": False,
            "inputs": [
                {"name": arg.name, "type": arg.typ.abi_type.selector_name()}
                for arg in fn.arguments
            ],
            "outputs": (
                [{"name": fn.name, "type": fn.return_type.abi_type.selector_name()}]
                if fn.return_type
                else []
            ),
            "name": f"__boa_private_{fn.name}__",
            "type": "function",
        }
        super().__init__(abi, contract._name)
        self.contract = contract
        self.func_t = fn

    @cached_property
    def source_code(self):
        return generate_source_for_internal_fn(self)


class ZksyncInternalVariable(_ZksyncInternal):
    def __init__(self, var: VarInfo, name: str, contract: ZksyncContract):
        abi = {
            "anonymous": False,
            "inputs": [],
            "outputs": [{"name": name, "type": var.typ.abi_type.selector_name()}],
            "name": f"__boa_private_{name}__",
            "type": "function",
        }
        super().__init__(abi, contract._name)
        self.contract = contract
        self.var = var
        self.var_name = name

    def get(self):
        return self.__call__()

    @cached_property
    def source_code(self):
        return textwrap.dedent(
            f"""
            @external
            @payable
            def __boa_private_{self.var_name}__() -> {self.var.typ.abi_type.selector_name()}:
                return self.{self.var_name}
        """
        )


class ZksyncEval(_ZksyncInternal):
    def __init__(self, code: str, contract: ZksyncContract):
        typ = detect_statement_type(code, contract)
        abi = {
            "anonymous": False,
            "inputs": [],
            "outputs": (
                [{"name": "eval", "type": typ.abi_type.selector_name()}] if typ else []
            ),
            "name": "__boa_debug__",
            "type": "function",
        }
        super().__init__(abi, contract._name)
        self.contract = contract
        self.code = code

    @cached_property
    def source_code(self):
        return generate_source_for_arbitrary_stmt(self.code, self.contract)
