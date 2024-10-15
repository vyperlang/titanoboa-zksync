import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Optional

import requests
from boa.util.abi import Address
from boa.verifiers import VerificationResult

DEFAULT_ZKSYNC_EXPLORER_URI = "https://zksync2-mainnet-explorer.zksync.io"


@dataclass
class ZksyncExplorer:
    """
    Allows users to verify contracts on the zksync explorer at https://explorer.zksync.io/
    This is independent of Vyper contracts, and can be used to verify any smart contract.
    """

    uri: str = DEFAULT_ZKSYNC_EXPLORER_URI
    api_key: Optional[str] = None  # todo: use or remove
    timeout: timedelta = timedelta(minutes=2)
    backoff: timedelta = timedelta(milliseconds=500)
    backoff_factor: float = 1.1
    retry_http_codes: tuple[int, ...] = (
        HTTPStatus.NOT_FOUND,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    )

    def verify(
        self,
        address: Address,
        contract_name: str,
        solc_json: dict,
        constructor_calldata: bytes = b"",
        wait: bool = False,
    ) -> Optional["VerificationResult"]:
        """
        Verify the Vyper contract on Blockscout.
        :param address: The address of the contract.
        :param contract_name: The name of the contract.
        :param solc_json: The solc_json output of the Vyper compiler.
        :param constructor_calldata: The calldata for the constructor.
        :param wait: Whether to return a VerificationResult immediately
                     or wait for verification to complete. Defaults to False
        """
        url = f"{self.uri}/contract_verification"

        body = {
            "contractAddress": address,
            "sourceCode": {
                contract_name if name == "<unknown>" else name: asset["content"]
                for name, asset in solc_json["sources"].items()
            },
            "codeFormat": "vyper-multi-file",
            "contractName": contract_name,
            "compilerVyperVersion": self._extract_version(
                solc_json["compiler_version"]
            ),
            "compilerZkvyperVersion": solc_json["zkvyper_version"],
            "constructorArguments": f"0x{constructor_calldata.hex()}",
            "optimizationUsed": True,
            # hardcoded in hardhat for some reason: https://github.com/matter-labs/hardhat-zksync/blob/187722e/packages/hardhat-zksync-verify-vyper/src/task-actions.ts#L110  # noqa: E501
        }

        response = requests.post(url, json=body)
        response.raise_for_status()
        verification_id = response.text
        int(verification_id)  # raises ValueError if not an int

        if not wait:
            return VerificationResult(verification_id, self)  # type: ignore

        self.wait_for_verification(verification_id)
        return None

    @staticmethod
    def _extract_version(version: str):
        # we only pass the first three digits of the version, as that's what the explorer expects
        match = re.search(r"(\d+\.\d+\.\d+)", version)
        assert match is not None, f"Could not extract version from {version}"
        return match.group(0)

    def wait_for_verification(self, verification_id: str) -> None:
        """
        Waits for the contract to be verified on Zksync Explorer.
        :param verification_id: The ID of the contract verification.
        """
        timeout = datetime.now() + self.timeout
        wait_time = self.backoff
        while datetime.now() < timeout:
            if self.is_verified(verification_id):
                print("Contract verified!")
                return
            time.sleep(wait_time.total_seconds())
            wait_time *= self.backoff_factor

        raise TimeoutError("Timeout waiting for verification to complete")

    def is_verified(self, verification_id: str) -> bool:
        url = f"{self.uri}/contract_verification/{verification_id}"

        response = requests.get(url)
        if response.status_code in self.retry_http_codes:
            return False
        response.raise_for_status()

        # known statuses: successful, failed, queued, in_progress
        json = response.json()
        if json["status"] == "failed":
            raise ValueError(f"Verification failed: {json['error']}")
        return json["status"] == "successful"
