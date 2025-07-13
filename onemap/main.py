# %%
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures._base import Future
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger
from tqdm import tqdm

from onemap import base_api_model

Result = dict[str, Any]
ResultList = list[Result]
Response = dict[str, ResultList | Any]


@dataclass
class OneMapAPI:
    email: str = os.getenv("ONEMAP_EMAIL", "")
    password: str = os.getenv("ONEMAP_EMAIL_PASSWORD", "")
    base_url: str = "https://www.onemap.gov.sg/api"
    backoff_multiplier: float = 1.5

    def __post_init__(self):
        """Initialize the OneMap API client with authentication"""
        if self.email and self.password:
            # Get access token for OneMap
            self._get_access_token()
            base_api_model._base_url = self.base_url
            base_api_model.set_credentials(self._access_token)

    def _get_access_token(self):
        """Get access token from OneMap API"""
        auth_url = f"{self.base_url}/auth/post/getToken"
        with httpx.Client() as client:
            response = client.post(
                auth_url, json={"email": self.email, "password": self.password}
            )
            response.raise_for_status()
            auth_data = response.json()
            self._access_token = auth_data["access_token"]
            self._access_token_expiry = int(auth_data["expiry_timestamp"])
            expiry_ds = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self._access_token_expiry)
            )
            logger.success(
                f"Access token obtained successfully. Expires at {expiry_ds}."
            )

    def _send_request(
        self,
        endpoint: str,
        method: str = "GET",
        backoff: float = 1,
        **kwargs,
    ) -> dict:
        try:
            response = base_api_model.request(method, endpoint, **kwargs)
            return json.loads(response.text)
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                logger.warning(
                    f"{method} request to {endpoint} failed with status code 429. Retrying after {backoff} seconds."
                )
                time.sleep(int(backoff))
                return self._send_request(
                    endpoint,
                    method,
                    backoff=backoff * self.backoff_multiplier,
                    **kwargs,
                )
            else:
                raise ValueError(f"Request failed: {str(e)}")

    def _reverse_search(self, endpoint: str, **kwargs) -> ResultList:
        kwargs = {"buffer": 40, "addressType": "All", "otherFeatures": "N", **kwargs}
        params = "&".join(f"{k}={v}" for k, v in kwargs.items())
        full_endpoint = (
            f"{endpoint}?{params}"
            if not endpoint.endswith("?")
            else f"{endpoint}{params}"
        )
        response = self._send_request(full_endpoint, "GET")
        return response.get("results", [])

    def search_xy(self, x_coord: float, y_coord: float) -> ResultList:
        return self._reverse_search(
            "/public/revgeocodexy", location=f"{x_coord},{y_coord}"
        )

    def search_latlon(self, lat: float, lon: float) -> ResultList:
        return self._reverse_search("/public/revgeocode", location=f"{lat},{lon}")

    def xy_to_latlon(self, x_coord: float, y_coord: float) -> Result:
        return self._convert("3414", "4326", X=x_coord, Y=y_coord)

    def latlon_to_xy(self, lat: float, lon: float) -> Result:
        return self._convert("4326", "3414", latitude=lat, longitude=lon)

    def _convert(self, from_format: str, to_format: str, **kwargs) -> Result:
        """
        Generic method to convert coordinates between specified coordinate reference systems.
        """
        params = "&".join(f"{k}={v}" for k, v in kwargs.items())
        endpoint = f"/common/convert/{from_format}to{to_format}?{params}"
        response = self._send_request(endpoint, "GET")
        return response

    def search(self, query: str) -> ResultList:
        """
        Perform a search using the OneMap API for each row in the given DataFrame.
        """
        endpoint = f"/common/elastic/search?searchVal={query}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        response: Response = self._send_request(endpoint, "GET")
        results: ResultList = response.get("results", [])
        results_with_query: ResultList = [
            {"query": query, **result} for result in results
        ]
        return results_with_query

    def searches(
        self, queries: list[str], max_workers: int = 5
    ) -> dict[str, ResultList]:
        """
        Perform parallel searches using a thread pool (no asyncio).
        """
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_query: dict[Future[ResultList], str] = {
                executor.submit(self.search, q): q for q in queries
            }
            results: dict[str, ResultList] = {}
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
