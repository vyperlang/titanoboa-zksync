from boa.rpc import EthereumRPC


class ZksyncRPC(EthereumRPC):

    _disabled_methods = {
        # zkSync Era does nothing with the max fee parameters.
        "maxPriorityFeePerGas": 0,
    }

    def fetch_uncached(self, method, params):
        if method in self._disabled_methods:
            return self._disabled_methods[method]
        return self.fetch(method, params)

    def fetch_multi(self, payloads):
        return [self.fetch(method, params) for method, params in payloads]
