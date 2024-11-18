import os
import socket
from datetime import datetime, timedelta
from subprocess import Popen, TimeoutExpired
from time import sleep

import requests
from requests.exceptions import ConnectionError


def find_free_port():
    # https://gist.github.com/bertjwregeer/0be94ced48383a42e70c3d9fff1f4ad0
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 0))
    portnum = s.getsockname()[1]
    s.close()
    return portnum


def wait_url(url: str):
    timeout = datetime.now() + timedelta(seconds=10)
    while datetime.now() < timeout:
        try:
            requests.head(url)
            return url
        except ConnectionError:
            sleep(0.1)
    raise TimeoutError(f"Could not connect to {url}")


def stop_subprocess(proc: Popen[bytes]):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except TimeoutExpired:  # pragma: no cover
        proc.kill()
        proc.wait(timeout=1)


def install_zkvyper_compiler(
    source="https://raw.githubusercontent.com/matter-labs/zkvyper-bin/v1.5.7/linux-amd64/zkvyper-linux-amd64-musl-v1.5.7",  # noqa: E501
    destination="/usr/local/bin/zkvyper",
):
    """
    Downloads the zkvyper binary from the given source URL and installs it to
    the destination directory.

    This is a very basic implementation - usually users want to install the binary
    manually, but in the Colab environment, we can automate this process.
    """
    response = requests.get(source)
    with open(destination, "wb") as f:
        f.write(response.content)

    os.chmod(destination, 0o755)  # make it executable
    assert os.system("zkvyper --version") == 0  # check if it works


def install_era_test_node(
    source="https://github.com/matter-labs/era-test-node/releases/download/v0.1.0-alpha.32/era_test_node-v0.1.0-alpha.32-x86_64-unknown-linux-gnu.tar.gz",  # noqa: E501
    destination="/usr/local/bin/era_test_node",
):
    """
    Downloads the era-test-node binary from the given source URL and installs it to
    the destination directory.

    This is a very basic implementation - usually users want to install the binary
    manually, but in the Colab environment, we can automate this process.
    """
    response = requests.get(source)
    with open("era_test_node.tar.gz", "wb") as f:
        f.write(response.content)

    os.system("tar --extract --file=era_test_node.tar.gz")
    os.system(f"mv era_test_node {destination}")
    os.system(f"{destination} --version")
    os.system("rm era_test_node.tar.gz")
