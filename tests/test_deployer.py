from boa.deployments import get_deployments_db

from boa_zksync.contract import ZksyncContract


def test_deployer_deploys(zksync_deployer):
    contract = zksync_deployer.deploy()
    db = get_deployments_db()
    deployments = db.get_deployments()

    assert isinstance(contract, ZksyncContract)
    assert len(deployments) == 1


def test_multiple_deploys(zksync_deployer):
    # TODO: This isn't quite working
    zksync_deployer.deploy()
    zksync_deployer.deploy()
    zksync_deployer.deploy()
    zksync_deployer.deploy()
    db = get_deployments_db()
    deployments = db.get_deployments()

    assert len(deployments) == 4
