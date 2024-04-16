try:
    from boa.integrations.jupyter import BrowserEnv
except ImportError:
    raise ModuleNotFoundError(
        "The `BrowserEnv` class requires Jupyter to be installed. "
        "Please be careful when importing the browser files outside of Jupyter env."
    )

from boa_zksync.environment import ZksyncEnv


class ZksyncBrowserEnv(ZksyncEnv, BrowserEnv):
    """
    A zkSync environment for deploying contracts using a browser wallet RPC.
    """
