import boa

from boa_zksync.environment import ZksyncEnv


def set_zksync_env(url):
    boa.set_env(ZksyncEnv.from_url(url))


def set_zksync_fork(url):
    boa.set_env(ZksyncEnv.from_url(url))
    boa.env.fork()


def set_zksync_browser_env(address=None):
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv

    boa.set_env(ZksyncBrowserEnv(address))


boa.set_zksync_env = set_zksync_env
boa.set_zksync_fork = set_zksync_fork
boa.set_zksync_browser_env = set_zksync_browser_env
