import textwrap

import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast
from vyper.exceptions import InvalidType
from vyper.semantics.analysis.utils import get_exact_type_from_node


def generate_source_for_internal_fn(fn):
    """Wraps internal fns with an external fn and generate source code"""

    fn_name = fn.func_t.name
    fn_args = ", ".join([arg.name for arg in fn.func_t.arguments])

    return_sig = ""
    fn_call = ""
    if fn.func_t.return_type:
        return_sig = f" -> {fn.func_t.return_type}"
        fn_call = "return "
    fn_call += f"self.{fn_name}({fn_args})"

    # same but with defaults, signatures, etc.:
    _fn_sig = []
    for arg in fn.func_t.arguments:
        sig_arg_text = f"{arg.name}: {arg.typ}"

        # check if arg has a default value:
        if arg.name in fn.func_t.default_values:
            default_value = fn.func_t.default_values[arg.name].value
            sig_arg_text += f" = {default_value}"

        _fn_sig.append(sig_arg_text)
    fn_sig = ", ".join(_fn_sig)

    return textwrap.dedent(
        f"""
        @external
        @payable
        def __boa_private_{fn_name}__({fn_sig}){return_sig}:
            {fn_call}
    """
    )


def generate_source_for_arbitrary_stmt(source_code, contract):
    """Wraps arbitrary stmts with external fn and generates source code"""

    ast_typ = detect_expr_type(source_code, contract)
    if ast_typ:
        return_sig = f"-> {ast_typ}"
        debug_body = f"return {source_code}"
    else:
        return_sig = ""
        debug_body = source_code

    # wrap code in function so that we can easily generate code for it
    return textwrap.dedent(
        f"""
        @external
        @payable
        def __boa_debug__() {return_sig}:
            {debug_body}
    """
    )


def detect_expr_type(source_code, contract):
    ast = parse_to_ast(source_code).body[0]
    if isinstance(ast, vy_ast.Expr):
        with contract.override_vyper_namespace():
            try:
                return get_exact_type_from_node(ast.value)
            except InvalidType:
                pass
    return None


def get_compiler_output(output):
    # we need this helper method to get the correct key containing compiler output
    # from the compiler. Assuming key names could change and also assuming that the
    # number of keys could change, this method breaks if any of that happens:

    excluded_keys = {"version", "zk_version", "__VYPER_MINIMAL_PROXY_CONTRACT", "extra_data"}
    contract_keys = set(output.keys()) - excluded_keys

    if len(contract_keys) != 1:
        unexpected = ", ".join(sorted(contract_keys))
        raise ValueError(f"Expected exactly one contract key, found {unexpected}")

    return output[next(iter(contract_keys))]
