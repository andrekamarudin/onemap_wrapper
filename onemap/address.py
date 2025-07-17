# %%
import os
import time
from typing import ClassVar, List, Optional

from loguru import logger
from returns.result import Result, safe

from onemap.base_api_model import BaseAPIModel, BaseClient, ResponseDict

api_client = BaseClient(_base_url="https://www.onemap.gov.sg/api")


def signin_onemap(email: Optional[str] = None, password: Optional[str] = None):
    """Set up authentication for the OneMap API client"""
    email = email or os.getenv("ONEMAP_EMAIL", "")
    password = password or os.getenv("ONEMAP_EMAIL_PASSWORD", "")

    # Create a temporary client without credentials for authentication
    import httpx

    with httpx.Client(base_url="https://www.onemap.gov.sg/api") as temp_client:
        response = temp_client.post(
            "auth/post/getToken",
            json={"email": email, "password": password},
        )
        response.raise_for_status()
        auth_data = response.json()
        token = auth_data["access_token"]
        expiry = int(auth_data["expiry_timestamp"])
        expiry_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry))
        logger.success(
            f"Successfully authenticated with OneMap API with expiry at {expiry_str}"
        )

        # Now set the credentials on our main client
        api_client.set_credentials(token)


class Address(BaseAPIModel):
    api_client: ClassVar[BaseClient] = api_client

    query_string: Optional[str] = None
    searchval: Optional[str] = None
    blk_no: Optional[str] = None
    road_name: Optional[str] = None
    building: Optional[str] = None
    address: Optional[str] = None
    postal: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def get_data(self) -> "Address":
        """
        Public method to perform search and populate address details.
        Returns Result indicating success or failure.
        """
        if not self.query_string:
            raise ValueError("query_string must be set before calling get_data")
        search_result: Result[List[ResponseDict], Exception] = self.search(
            self.query_string
        )
        if isinstance(search_result, Exception):
            raise search_result.failure()
        results: List[ResponseDict] = search_result.unwrap()

        # Take the first result
        first_result: ResponseDict = results[0]
        for field_name, field_value in first_result.items():
            if hasattr(self, field_name.lower()):
                setattr(self, field_name.lower(), field_value)
        return self

    @classmethod
    @safe
    def search(cls, query: str) -> List[ResponseDict]:
        response: ResponseDict = cls.api_client.get(
            endpoint="common/elastic/search",
            params={"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y"},
        )
        results: list[ResponseDict] = response.get("results", [])
        return results


if __name__ == "__main__":
    signin_onemap()
    myhome = Address(query_string="61 citylife")
    myhome.get_data()
    print(myhome)
