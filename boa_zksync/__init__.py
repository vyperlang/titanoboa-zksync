import boa
from boa_zksync.env import ZksyncEnv
from boa_zksync.interpret import compile_zksync, load_zksync, loads_zksync, load_zksync_partial, loads_zksync_partial, eval_zksync

boa.compile_zksync = compile_zksync
boa.load_zksync = load_zksync
boa.loads_zksync = loads_zksync
boa.load_zksync_partial = load_zksync_partial
boa.loads_zksync_partial = loads_zksync_partial
boa.eval_zksync = eval_zksync


def set_zksync_env(url):
    boa.env = ZksyncEnv.from_url(url)


def set_zksync_browser_env(address=None):
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv
    boa.env = ZksyncBrowserEnv(address)
