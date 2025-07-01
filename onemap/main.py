# %%
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests
from icecream import ic  # noqa
from loguru import logger
from tqdm import tqdm


@dataclass
class OneMapAPI:
    email: str = os.getenv("ONEMAP_EMAIL", "")
    password: str = os.getenv("ONEMAP_EMAIL_PASSWORD", "")
    base_url: str = "https://www.onemap.gov.sg/api"
    backoff_multiplier: float = 1.5

    def _send_request(
        self,
        url: str,
        method: str = "GET",
        with_headers: bool = True,
        backoff: float = 1,
        **kwargs,
    ) -> dict:
        response = requests.request(
            method, url, headers=self.headers if with_headers else None, **kwargs
        )
        if response.status_code == 429:
            endpoint = url.replace(self.base_url, "").replace("?*", "")
            logger.warning(
                f"{method} request to {endpoint} failed with status code 429. Retrying after {backoff} seconds."
            )
            time.sleep(int(backoff))
            return self._send_request(
                url,
                method,
                with_headers,
                backoff=backoff * self.backoff_multiplier,
                **kwargs,
            )
        elif response.status_code >= 300:
            raise ValueError(
                f"Request failed with status code {response.status_code} and response {response.text}"
            )
        return json.loads(response.text)

    @property
    def headers(self) -> dict:
        if hasattr(self, "_headers") and self._access_token_expiry > time.time():
            return self._headers
        elif self.email and self.password:
            self._headers: dict[str, str] = {"Authorization": self.access_token}
        else:
            raise ValueError(
                "Either access_token or email and password must be provided."
            )
        return self._headers

    @property
    def access_token(self) -> str:
        if (
            not hasattr(self, "_access_token")
            or time.time() > self._access_token_expiry
        ):
            response = self._send_request(
                url=f"{self.base_url}/auth/post/getToken",
                method="POST",
                json={"email": self.email, "password": self.password},
                with_headers=False,
            )
            self._access_token = response["access_token"]
            self._access_token_expiry = int(response["expiry_timestamp"])
        return self._access_token

    def _reverse_search(self, url: str, **kwargs) -> list[dict[str, Any]]:
        kwargs = {"buffer": 40, "addressType": "All", "otherFeatures": "N", **kwargs}
        url += "&".join(f"{k}={v}" for k, v in kwargs.items())
        response = self._send_request(url, "GET")
        return response.get("results", [])

    def search_xy(self, x_coord: float, y_coord: float) -> list[dict[str, Any]]:
        return self._reverse_search(
            f"{self.base_url}/public/revgeocodexy?", location=f"{x_coord},{y_coord}"
        )

    def search_latlon(self, lat: float, lon: float) -> list[dict[str, Any]]:
        return self._reverse_search(
            f"{self.base_url}/public/revgeocode?", location=f"{lat},{lon}"
        )

    def xy_to_latlon(self, x_coord: float, y_coord: float):
        return self._convert("3414", "4326", X=x_coord, Y=y_coord)

    def latlon_to_xy(self, lat: float, lon: float):
        return self._convert("4326", "3414", latitude=lat, longitude=lon)

    def _convert(self, from_format: str, to_format: str, **kwargs) -> dict[str, Any]:
        """
        Generic method to convert coordinates between specified coordinate reference systems.
        """
        url = f"{self.base_url}/common/convert/{from_format}to{to_format}?"
        url += "&".join(f"{k}={v}" for k, v in kwargs.items())
        response = self._send_request(url, "GET")
        return response

    def search(self, query: str) -> list[dict[str, Any]]:
        """
        Perform a search using the OneMap API for each row in the given DataFrame.
        """
        url = f"{self.base_url}/common/elastic/search?searchVal={query}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        response: dict = self._send_request(url, "GET")
        results: list[dict] = response.get("results", [])
        results_with_query: list[dict[str, Any]] = [
            {"query": query, **result} for result in results
        ]
        return results_with_query

    def searches(
        self, queries: list[str], max_workers: int = 5
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Perform parallel searches using a thread pool (no asyncio).
        """
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_query = {executor.submit(self.search, q): q for q in queries}
            results: dict[str, list[dict[str, Any]]] = {}
            for fut in tqdm(
                as_completed(future_to_query),
                total=len(queries),
                desc="Searching OneMap",
                unit="query",
            ):
                q = future_to_query[fut]
                try:
                    results[q] = fut.result()
                except Exception as e:
                    results[q] = [{"error": str(e)}]
        return results


def main():
    onemap = OneMapAPI()
    print(
        onemap.xy_to_latlon(
            x_coord=28983.788791079794,
            y_coord=33554.5098132845,
        )
    )


if __name__ == "__main__":
    main()
