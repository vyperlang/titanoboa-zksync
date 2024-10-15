from boa.deployments import get_deployments_db

from boa_zksync.contract import ZksyncContract


def test_deployer_deploys(zksync_deployer):
    contract = zksync_deployer.deploy()
    zk_data = zksync_deployer.zkvyper_data
    db = get_deployments_db()
    (deployment,) = list(db.get_deployments())
    assert isinstance(contract, ZksyncContract)
    deployed_code = deployment.source_code["sources"]["<unknown>"]["content"]
    assert deployed_code == zk_data.source_code
    assert deployment.tx_dict["bytecode"] == f"0x{zk_data.bytecode.hex()}"


def test_multiple_deploys(zksync_deployer):
    db = get_deployments_db()
    initial_count = len(list(db.get_deployments()))  # db is shared across module
    zksync_deployer.deploy()
    zksync_deployer.deploy()
    zksync_deployer.deploy()
    zksync_deployer.deploy()
    assert len(list(db.get_deployments())) == 4 + initial_count
