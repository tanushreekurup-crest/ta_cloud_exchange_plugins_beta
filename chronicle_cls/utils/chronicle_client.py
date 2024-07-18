"""
BSD 3-Clause License

Copyright (c) 2021, Netskope OSS
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

"""CLS Google Chronicle Plugin Client."""


import json
import sys
import traceback

import requests
from google.auth.transport import requests as gRequest
from google.oauth2 import service_account

from .chronicle_constants import DEFAULT_URL, SCOPES
from .chronicle_exceptions import GoogleChroniclePluginException


class ChronicleClient:
    """Chronicle Client."""

    def __init__(self, configuration: dict, logger, log_prefix, plugin_name):
        """Initialize."""
        self.configuration = configuration
        self.logger = logger
        self.log_prefix = log_prefix
        self.plugin_name = plugin_name
        self.create_session()

    def create_session(self):
        """To Create a new session with credentials to make push requests."""
        try:
            credentials = (
                service_account.Credentials.from_service_account_info(
                    json.loads(self.configuration["service_account_key"]),
                    scopes=SCOPES,
                )
            )
            self.http_session = gRequest.AuthorizedSession(credentials)
        except Exception:
            raise

    def ingest(
        self,
        transformed_data,
        headers,
        is_validate=False,
        page=0,
        data_type=None,
        subtype=None,
    ):
        """Call the API for data Ingestion.

        :transformed_data : The transformed data to be ingested.
        """
        try:
            if self.configuration.get("region", "") == "custom":
                BASE_URL = self.configuration.get("custom_region", "")
            else:
                BASE_URL = DEFAULT_URL[self.configuration.get("region", "usa")]

            url = f"{BASE_URL}/v2/udmevents:batchCreate"
            payload = {
                "customer_id": self.configuration["customer_id"].strip(),
                "events": transformed_data,
            }
            chunk_size = sys.getsizeof(payload)
            log_msg = (
                f"[{data_type}] [{subtype}] - Ingesting logs for"
                f" page {page} to {self.plugin_name}. No of logs"
                f" in payload: {len(payload['events'])}, Chunk Size: "
                f"{chunk_size} Bytes."
            )
            self.logger.debug(f"{self.log_prefix}: {log_msg}")
            response = self.http_session.request(
                "POST",
                url,
                headers=headers,
                json=payload,
            )
            status_code = response.status_code
            self.logger.debug(
                f"{self.log_prefix}: Received API Response for page {page}."
                f" Status Code = {status_code}"
            )
            if status_code != 200:
                err_msg = (
                    f"Unable to send the logs to {self.plugin_name}"
                    f" for page {page}."
                )
                self.logger.error(
                    message=f"{self.log_prefix}: {err_msg}",
                    details=f"API Response: {str(response.text)}",
                )
            else:
                try:
                    response = response.json()
                except json.JSONDecodeError as err:
                    err_msg = (
                        "Invalid JSON response received from API."
                        f" Error: {err}"
                    )
                    self.logger.error(
                        message=f"{self.log_prefix}: {err_msg}",
                        details=f"API response: {response.text}",
                    )
                    raise GoogleChroniclePluginException(err_msg)
                except Exception as exp:
                    err_msg = (
                        "Unexpected error occurred while parsing"
                        f" json response. Error: {exp}"
                    )
                    self.logger.error(
                        message=f"{self.log_prefix}: {err_msg}",
                        details=f"API response: {response.text}",
                    )
                    raise GoogleChroniclePluginException(err_msg)

            if is_validate and response == {}:
                return True

            if response == {}:
                return

            status_code = response.get("error").get("code")
            message = response.get("error").get("message")
            status = response.get("error").get("status")

            if status in ["FAILED_PRECONDITION", "PERMISSION_DENIED"]:
                raise Exception(f"Invalid Customer ID provided. {message}")
            if status in ["INVALID_ARGUMENT"]:
                raise Exception(f"Invalid UDM event provided. {message}")
            raise Exception(
                f"status_code: {status_code}, message: {message}, status: {status}"
            )

        except requests.exceptions.HTTPError as err:
            err_msg = "HTTP Error occurred while ingesting data."
            self.logger.error(
                message=f"{self.log_prefix}: {err_msg} Error: {err}.",
                details=str(traceback.format_exc()),
            )
            raise GoogleChroniclePluginException(err_msg)
        except requests.exceptions.ConnectionError as err:
            err_msg = (
                f"Unable to establish connection with {self.plugin_name} "
                "while ingesting data. "
                "Check Region or Custom URL provided in configuration parameter."
            )
            self.logger.error(
                message=f"{self.log_prefix}: {err_msg} Error: {err}.",
                details=str(traceback.format_exc()),
            )
            raise GoogleChroniclePluginException(err_msg)
        except requests.exceptions.Timeout as err:
            err_msg = "Request timed out while ingesting data."
            self.logger.error(
                message=f"{self.log_prefix}: {err_msg} Error: {err}.",
                details=str(traceback.format_exc()),
            )
            raise GoogleChroniclePluginException(err_msg)
        except GoogleChroniclePluginException:
            raise
        except Exception as err:
            err_msg = (
                "Unexpected error occurred while requesting to "
                f"{self.plugin_name} server while ingesting data. Error: {err}"
            )
            self.logger.error(
                message=f"{self.log_prefix}: {err_msg}",
                details=str(traceback.format_exc()),
            )
            raise GoogleChroniclePluginException(err_msg)
