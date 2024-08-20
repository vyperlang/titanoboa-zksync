import pytest

from boa_zksync.compiler_utils import get_compiler_output


def test_get_compiler_output():

    output_dict = {"blabla": 123, "zk_version": 456, "version": 789}

    assert get_compiler_output(output_dict) == 123


def test_get_compiler_output_too_many_keys():

    output_dict = {
        "blabla": 123,
        "zk_version": 456,
        "version": 789,
        "new_compiler_output_key": 101112,
    }

    with pytest.raises(
        ValueError,
        match="Expected exactly one contract key, found blabla, new_compiler_output_key",
    ):
        get_compiler_output(output_dict)


def test_get_compiler_output_unexpected_key():

    output_dict = {"blabla": 123, "zk_versions": 456, "version": 789}

    with pytest.raises(
        ValueError, match="Expected exactly one contract key, found blabla, zk_versions"
    ):
        get_compiler_output(output_dict)
