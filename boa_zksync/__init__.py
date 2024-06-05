import boa

from boa_zksync.environment import ZksyncEnv
from boa_zksync.node import EraTestNode


def set_zksync_env(url):
    boa.set_env(ZksyncEnv.from_url(url))


def set_zksync_test_env(node_args=()):
    boa.set_env(ZksyncEnv(rpc=EraTestNode(node_args=node_args)))


def set_zksync_fork(url, *args, **kwargs):
    env = ZksyncEnv.from_url(url)
    env.fork(*args, **kwargs)
    boa.set_env(env)


def set_zksync_browser_env(*args, **kwargs):
    # import locally because jupyter is generally not installed
    from boa_zksync.browser import ZksyncBrowserEnv

    boa.set_env(ZksyncBrowserEnv(*args, **kwargs))


boa.set_zksync_env = set_zksync_env
boa.set_zksync_test_env = set_zksync_test_env
boa.set_zksync_fork = set_zksync_fork
boa.set_zksync_browser_env = set_zksync_browser_env
