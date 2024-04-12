import boa

from boa_zksync.env import ZksyncEnv
from boa_zksync.interpret import compile_zksync, load_zksync, loads_zksync, load_zksync_partial, loads_zksync_partial, eval_zksync


def set_zksync_env(url):
    boa.set_env(ZksyncEnv.from_url(url))


def set_zksync_browser_env(address=None):
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv
    from boa.integrations.jupyter import browser

    # Set a larger shared memory as the zkSync transactions are larger
    browser.SHARED_MEMORY_LENGTH = 100 * 1024 + 1
    boa.set_env(ZksyncBrowserEnv(address))


boa.compile_zksync = compile_zksync
boa.load_zksync = load_zksync
boa.loads_zksync = loads_zksync
boa.load_zksync_partial = load_zksync_partial
boa.loads_zksync_partial = loads_zksync_partial
boa.eval_zksync = eval_zksync
boa.set_zksync_env = set_zksync_env
boa.set_zksync_browser_env = set_zksync_browser_env
