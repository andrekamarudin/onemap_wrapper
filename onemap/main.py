# %%
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Coroutine

import requests
from tqdm import tqdm


@dataclass
class OneMapAPI:
    email: str = os.getenv("ONEMAP_EMAIL", "")
    password: str = os.getenv("ONEMAP_EMAIL_PASSWORD", "")
    access_token: str = os.getenv("ONEMAP_ACCESS_TOKEN", "")

    def _send_request(
        self, url: str, method: str = "GET", with_headers: bool = True, **kwargs
    ) -> dict:
        response = requests.request(
            method, url, headers=self.headers if with_headers else None, **kwargs
        )
        if response.status_code >= 300:
            raise ValueError(
                f"Request failed with status code {response.status_code} and response {response.text}"
            )
        return json.loads(response.text)

    @property
    def headers(self) -> dict:
        if hasattr(self, "_headers"):
            return self._headers
        elif hasattr(self, "access_token") and self.access_token:
            self._headers = {"accessToken": self.access_token}
        elif self.email and self.password:
            url = "https://www.onemap.gov.sg/api/auth/post/getToken"
            payload = {"email": self.email, "password": self.password}
            self._headers = self._send_request(
                url, "POST", json=payload, with_headers=False
            )
        else:
            raise ValueError(
                "Either access_token or email and password must be provided."
            )
        return self._headers

    def reverse_search(self, x_coord: float, y_coord: float) -> list[dict[str, Any]]:
        """
        Reverse search for an address using coordinates.
        """
        url = f"https://www.onemap.gov.sg/api/public/revgeocodexy?location={x_coord}%2C{y_coord}&buffer=40&addressType=All&otherFeatures=N"

        response = self._send_request(url, "GET")
        return response.get("results", [])

    def xy_to_latlon(self, x_coord: float, y_coord: float):
        url = f"https://www.onemap.gov.sg/api/common/convert/3414to4326?X={x_coord}&Y={y_coord}"

        response = self._send_request(url, "GET")
        return response

    def search(self, query: str) -> list[dict[str, Any]]:
        """
        Perform a search using the OneMap API for each row in the given DataFrame.
        """
        url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={query}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        response: dict = self._send_request(url, "GET")
        results: list[dict] = response.get("results", [])
        results_with_query: list[dict[str, Any]] = [
            {"query": query, **result} for result in results
        ]
        return results_with_query

    def searches(
        self,
        queries: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Perform asynchronous searches using the OneMap API for each query in the list.
        """

        qbar = tqdm(
            total=len(queries),
            desc="Searching OneMap",
            unit="query",
            leave=False,
            position=0,
        )

        dict_of_results: dict[str, list[dict[str, Any]]] = {}

        def _search(query: str):
            results: list[dict[str, Any]] = self.search(query)
            dict_of_results[query] = results
            qbar.update(1)

        async def _async(queries: list[str]):
            tasks: list[Coroutine] = [
                asyncio.to_thread(_search, query) for query in queries
            ]
            await asyncio.gather(*tasks)

        asyncio.run(_async(queries))

        return dict_of_results
