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
