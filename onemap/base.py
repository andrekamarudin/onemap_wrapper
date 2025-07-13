import types
from typing import ClassVar, Generic, Type, TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound="BaseAPIModel")

_client = None
_token = None
_base_url = "http://localhost:8000"


def set_credentials(token: str):
    global _client, _token, _base_url
    _token = token
    _client = httpx.Client(
        base_url=_base_url, headers={"Authorization": f"Bearer {_token}"}
    )


def request(method: str, endpoint: str, **kwargs) -> httpx.Response:
    if _client is None:
        raise RuntimeError("Credentials not set. Call set_credentials() first.")
    response = _client.request(method, endpoint, **kwargs)
    response.raise_for_status()
    return response


def get(endpoint: str, params: dict | None = None) -> httpx.Response:
    return request("GET", endpoint, params=params)


def post(endpoint: str, json: dict | None = None) -> httpx.Response:
    return request("POST", endpoint, json=json)


def put(endpoint: str, json: dict | None = None) -> httpx.Response:
    return request("PUT", endpoint, json=json)


def delete(endpoint: str) -> httpx.Response:
    return request("DELETE", endpoint)


client = types.SimpleNamespace(
    get=get,
    post=post,
    put=put,
    delete=delete,
)


class BaseAPIModel(BaseModel, Generic[T]):
    id: str | None = None
    _resource_path: ClassVar[str] = ""

    def save(self) -> None:
        data = self.model_dump(exclude_unset=True)
        if self.id:
            response = client.put(f"/{self._resource_path}/{self.id}", json=data)
        else:
            response = client.post(f"/{self._resource_path}", json=data)
        response.raise_for_status()
        self.id = response.json()["id"]

    def delete(self) -> None:
        if not self.id:
            raise ValueError("Cannot delete unsaved resource.")
        response = client.delete(f"/{self._resource_path}/{self.id}")
        response.raise_for_status()

    @classmethod
    def load(cls: Type[T], resource_id: str) -> T:
        response = client.get(f"/{cls._resource_path}/{resource_id}")
        if response.status_code == 404:
            raise ValueError(f"{cls.__name__} not found.")
        response.raise_for_status()
        return cls(**response.json())

    @classmethod
    def find(cls: Type[T]) -> list[T]:
        response = client.get(f"/{cls._resource_path}")
        response.raise_for_status()
        return [cls(**item) for item in response.json()]
