# %%
import asyncio
import json
import os
from dataclasses import dataclass

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

    def search(self, query: str) -> list[dict]:
        """
        Perform a search using the OneMap API for each row in the given DataFrame.
        """
        url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={query}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        result = self._send_request(url, "GET")
        return result.get("results", [])

    async def search_async(self, queries: list[str]) -> list[dict[str, object]]:
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

        def search_and_update(query: str) -> dict[str, object]:
            results = self.search(query)
            qbar.update(1)
            return {
                "query": query,
                "results": results,
            }

        tasks = [asyncio.to_thread(search_and_update, query) for query in queries]
        results = await asyncio.gather(*tasks)

        return results
