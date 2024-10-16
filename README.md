# titanoboa-zksync
A Zksync plugin for the Titanoboa Vyper interpreter


## Installation

First install the following dependencies, depending on your system:

#### Google Colab
For Google Colab: The following dependencies should be downloaded automatically.

#### Zkvyper Compiler
We use the [era-compiler-vyper](https://github.com/matter-labs/era-compiler-vyper) a.k.a. `zkvyper`: to compile Vyper code to ZkSync-compatible bytecode.

1. Download the latest binary from the [zkvyper-bin repository](https://github.com/matter-labs/zkvyper-bin) and rename it as `zkvyper`.
 
2. On Linux/macOS, mark the binary as executable:
`chmod a+x <path to file>`

3. On macOS, the binary may need to have its quarantine attribute cleared: 
`xattr -d com.apple.quarantine <path to file>`

Then, make sure this is available in your system PATH.

#### ZkSync Node

If you want to test with forks or a local test node, you will need to install the ZkSync [era-test-node](https://github.com/matter-labs/era-test-node/releases).

1. Download `era-test-node` from latest [Release](https://github.com/matter-labs/era-test-node/releases/latest)

2. Extract the binary and mark as executable:
   ```bash
   tar xz -f era_test_node.tar.gz -C /usr/local/bin/
   chmod +x /usr/local/bin/era_test_node
   ```

Then, make sure this is available in your system PATH.

#### Install the plugin
Finally, install the package:

```bash
pip install titanoboa-zksync
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
