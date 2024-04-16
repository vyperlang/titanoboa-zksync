import boa

from boa_zksync.environment import ZksyncEnv
from boa_zksync.interpret import (
    compile_zksync,
    eval_zksync,
    load_zksync,
    load_zksync_partial,
    loads_zksync,
    loads_zksync_partial,
)


def set_zksync_env(url):
    boa.set_env(ZksyncEnv.from_url(url))


def set_zksync_browser_env(address=None):
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv

    boa.set_env(ZksyncBrowserEnv(address))


boa.compile_zksync = compile_zksync
boa.load_zksync = load_zksync
boa.loads_zksync = loads_zksync
boa.load_zksync_partial = load_zksync_partial
boa.loads_zksync_partial = loads_zksync_partial
boa.eval_zksync = eval_zksync
boa.set_zksync_env = set_zksync_env
boa.set_zksync_browser_env = set_zksync_browser_env

