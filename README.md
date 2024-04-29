# titanoboa-zksync
A Zksync plugin for the Titanoboa Vyper interpreter


## Installation

First install the following dependencies, depending on your system:

- [era-compiler-vyper]() a.k.a. `zkvyper`: to compile Vyper code to ZkSync-compatible bytecode.
- [era-test-node]( https://github.com/matter-labs/era-test-node/releases) for testing and forking. 

For Google Colab: These dependencies should be downloaded automatically.

Then, install the package:

```bash
pip install git+https://github.com/DanielSchiavini/titanoboa-zksync.git@main
```

## Usage
The usage of this plugin is similar to the original [Titanoboa interpreter](https://github.com/vyperlang/titanoboa).

Note that the boa_zksync plugin must be imported to install the hooks in the `boa` object.
The same functions are also available in the `boa_zksync` module.


### Configuring the environment
#### In Python:
```python
import boa, boa_zksync

boa.set_zksync_env("<rpc-url>")
```

#### In JupyterLab or Google Colab:
```python
import boa, boa_zksync

boa.set_zksync_browser_env()
boa.env.set_chain_id(324)  # Set the chain ID to the ZkSync network
```

Some cell magic is also provided after the extension is loaded:
```jupyter
%load_ext boa_zksync.ipython
```

Instead of `loads_zksync_partial` you can use:
```jupyter
%zkvyper ContractName
# put your source code here, a deployer object with this name is created.
```

Instead of `load_zksync` you can then use:
```jupyter
%zkcontract
# put your source code here, a contract will be deployed to ZkSync
```

Instead of `eval_zksync` you can use:
```jupyter
%zkeval
# put some code to be evaluated here
```

### Interacting with the network

```python
import boa, boa_zksync

constructor_args, address = [], "0x1234..."

# Compile a contract from source file
boa.compile_zksync("path/to/contract.vy")

# Load a contract from source code and deploy
boa.loads_zksync("contract source code", *constructor_args)

# Load a contract from file and deploy
contract = boa.load_zksync("path/to/contract.vy", *constructor_args)

# Load a contract from source file but don't deploy yet
deployer = boa.load_zksync_partial("source code")
deployer.deploy(*constructor_args)  # Deploy the contract
deployer.at(address) # Connect a contract to an existing address

# Load a contract from source file but don't deploy yet
deployer = boa.loads_zksync_partial("source code")
deployer.deploy(*constructor_args)  # Deploy the contract
deployer.at(address) # Connect a contract to an existing address

# Run the given source code directly
boa.eval_zksync("source code")
```

### Limitations
- `# pragma optimize gas` is not supported by Zksync
