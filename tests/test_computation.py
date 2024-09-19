import boa

from boa_zksync.types import ZksyncComputation

_required_fields = {"gas": "0x0", "value": "0x0", "input": "0x00", "gasUsed": "0x0"}


def test_from_debug_trace_nested():
    sender = boa.env.generate_address()
    to = boa.env.generate_address()
    result = boa.env.generate_address().canonical_address
    output = {
        "from": sender,
        "to": to,
        "output": boa.env.generate_address(),
        "calls": [
            {
                "from": boa.env.generate_address(),
                "to": boa.env.generate_address(),
                "output": boa.env.generate_address(),
                "calls": [],
                **_required_fields,
            },
            {
                "from": sender,
                "to": to,
                "output": "0x" + result.hex(),
                "calls": [],
                **_required_fields,
            },
            {
                "from": boa.env.generate_address(),
                "to": boa.env.generate_address(),
                "output": boa.env.generate_address(),
                "calls": [],
                **_required_fields,
            },
        ],
    }
    assert ZksyncComputation.from_debug_trace(boa.env, output).output == result


def test_from_debug_trace_production_mode():
    # in production the real transaction output is directly in the result
    # when running via the era test node, more contracts are actually included
    result = boa.env.generate_address().canonical_address
    output = {
        "from": boa.env.generate_address(),
        "to": boa.env.generate_address(),
        "output": "0x" + result.hex(),
        "calls": [],
        **_required_fields,
    }
    assert ZksyncComputation.from_debug_trace(boa.env, output).output == result
