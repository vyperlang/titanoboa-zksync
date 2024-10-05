import boa

from boa_zksync.environment import ZksyncEnv
from boa_zksync.node import EraTestNode


def set_zksync_env(url, nickname=None):
    boa.set_env(ZksyncEnv.from_url(url, nickname=nickname))


def set_zksync_test_env(node_args=(), nickname=None):
    boa.set_env(ZksyncEnv(rpc=EraTestNode(node_args=node_args), nickname=nickname))


def set_zksync_fork(url, nickname=None, *args, **kwargs):
    env = ZksyncEnv.from_url(url, nickname=nickname)
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
