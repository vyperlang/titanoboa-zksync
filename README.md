# titanoboa-zksync
A Zksync plugin for the Titanoboa Vyper interpreter


## Installation

First install the following dependencies, depending on your system:

- [era-compiler-vyper](https://github.com/matter-labs/era-compiler-vyper) a.k.a. `zkvyper`: to compile Vyper code to ZkSync-compatible bytecode.
- [era-test-node]( https://github.com/matter-labs/era-test-node/releases) for testing and forking. 

For Google Colab: These dependencies should be downloaded automatically.

Then, install the package:

```bash
pip install git+https://github.com/DanielSchiavini/titanoboa-zksync.git@main
```

## Usage
The usage of this plugin is similar to the original [Titanoboa interpreter](https://github.com/vyperlang/titanoboa).

### Configuring the environment
#### In Python:

```python
import boa_zksync

boa_zksync.set_zksync_env("<rpc_url>")  # use RPC
boa_zksync.set_zksync_fork("<rpc_url>")  # fork from the mainnet
boa_zksync.set_zksync_test_env()  # run a local test node
```

#### In JupyterLab or Google Colab:
```python
import boa, boa_zksync
from boa.integrations.jupyter import BrowserSigner

# use the browser signer and RPC:
boa_zksync.set_zksync_browser_env()  # use the browser signer and RPC
boa.env.set_chain_id(324)  # Set the chain ID to the ZkSync network

# use the browser signer and a custom RPC:
boa_zksync.set_zksync_env("<rpc_url>")
boa.env.set_eoa(BrowserSigner())
```

### Interacting with the network

```python
import boa, boa_zksync

constructor_args, address = [], "0x1234..."

boa_zksync.set_zksync_test_env()  # configure the environment, see previous section

# Compile a contract from source file
boa_zksync.ZksyncDeployer.create_compiler_data("source code")

# Load a contract from source code and deploy
boa.loads("contract source code", *constructor_args)

# Load a contract from file and deploy
contract = boa.load("path/to/contract.vy", *constructor_args)

# Load a contract from source file but don't deploy yet
deployer = boa.loads_partial("source code")
deployer.deploy(*constructor_args)  # Deploy the contract
deployer.at(address) # Connect a contract to an existing address

# Load a contract from source file but don't deploy yet
deployer = boa.loads_partial("source code")
deployer.deploy(*constructor_args)  # Deploy the contract
deployer.at(address) # Connect a contract to an existing address

# Run the given source code directly
boa.eval("source code")
```

### Limitations
- `# pragma optimize gas` is not supported by Zksync
