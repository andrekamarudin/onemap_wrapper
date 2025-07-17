from dataclasses import dataclass
from typing import Any, ClassVar, Generic, Type, TypeVar

import httpx
from pydantic import BaseModel

ResponseDict = dict[str, Any]


@dataclass
class BaseClient:
    """HTTP client for API methods."""

    _client: httpx.Client | None = None
    _token: str | None = None
    _base_url: str | None = None

    def set_credentials(self, token: str):
        self._token = token
        if self._base_url is None:
            raise ValueError("Base URL must be set before setting credentials")
        self._client = httpx.Client(
            base_url=self._base_url, headers={"Authorization": self._token}
        )

    def _request(self, method: str, endpoint: str, **kwargs) -> ResponseDict:
        """Make an HTTP request to the API."""
        if self._client is None:
            raise RuntimeError("Credentials not set. Call set_credentials() first.")
        response = self._client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        return response.json()

    def get(self, endpoint: str, **kwargs) -> ResponseDict:
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> ResponseDict:
        return self._request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> ResponseDict:
        return self._request("PUT", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> ResponseDict:
        return self._request("DELETE", endpoint, **kwargs)


T = TypeVar("T", bound="BaseAPIModel")


class BaseAPIModel(BaseModel, Generic[T]):
    api_client: ClassVar[BaseClient]
    id: str | None = None
    _resource_path: ClassVar[str] = ""

    def save(self) -> ResponseDict:
        """Save the model instance to the API."""
        data = self.model_dump(exclude_unset=True)
        if self.id:
            response = self.api_client.put(
                f"/{self._resource_path}/{self.id}", json=data
            )
        else:
            response = self.api_client.post(f"/{self._resource_path}", json=data)
        self.id = response["id"]
        return response

    def delete(self) -> ResponseDict:
        """Delete the model instance from the API."""
        if not self.id:
            raise ValueError("Cannot delete unsaved resource.")
        return self.api_client.delete(f"/{self._resource_path}/{self.id}")

    @classmethod
    def load(cls: Type[T], resource_id: str) -> T:
        """Load a resource by its ID."""
        response = cls.api_client.get(f"/{cls._resource_path}/{resource_id}")
        return cls(**response)

    @classmethod
    def find(cls: Type[T]) -> list[T]:
        """Find all resources of this type."""
        response: ResponseDict = cls.api_client.get(f"/{cls._resource_path}")
        return [cls(**response)]
