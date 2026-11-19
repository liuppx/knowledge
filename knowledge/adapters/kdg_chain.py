"""知行图(KnowDoGraph)链的适配器:上传正文、查成员与单元、提交已签名的操作。

只走知行图浏览器服务的公开接口(规范见知行图仓库 docs/API.md 与 docs/design/ontology-v0.1.md):

- ``PUT  /bodies/<sha256>``        上传正文(需写入令牌;服务端校验哈希,内容寻址、不可变)
- ``GET  /lookup?pubkey=<hex>``    公钥对应的成员(账户号、是否已过见习期)
- ``GET  /lookup?body=<sha256>``   正文落在哪个单元的哪些版本
- ``GET  /rpc/unit/<id>``          单元详情;``GET /rpc/account/<id>`` 账户(序号 nonce)
- ``POST /rpc/knowledge``          提交 op ‖ 签名(需写入令牌;签名由用户的钱包完成)

写入令牌只防刷写入,不代表身份;身份由钱包的签名证明。
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from knowledge.core.settings import get_settings


class KdgChainError(RuntimeError):
    """链或浏览器服务返回了错误(网络错误、4xx/5xx)。"""


class KdgChainPort(Protocol):
    def put_body(self, sha256: str, body: bytes) -> str: ...
    def lookup_member(self, pubkey: str) -> dict | None: ...
    def lookup_body(self, sha256: str) -> dict | None: ...
    def get_unit(self, unit_id: int) -> dict | None: ...
    def get_nonce(self, account: int) -> int: ...
    def submit_op(self, signed: bytes, *, intent: dict | None = None) -> str: ...
    def unit_url(self, unit_id: int) -> str: ...
    def list_domains(self) -> list[dict]: ...


def _domains_from_scheme(scheme: dict) -> list[dict]:
    """知行图领域概念方案(/id/domain,SKOS)→ [{id, name_zh, name_en}]。"""
    out = []
    for concept in scheme.get("concepts") or []:
        labels = concept.get("prefLabel") or {}
        try:
            out.append({"id": int(concept.get("notation")), "name_zh": labels.get("zh") or "", "name_en": labels.get("en") or ""})
        except (TypeError, ValueError):
            continue
    return sorted(out, key=lambda d: d["id"])


class LiveKdgChain:
    """连接真实的知行图浏览器服务。"""

    def __init__(self, base_url: str, write_token: str, *, timeout_seconds: float = 30.0, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = write_token
        self.client = client or httpx.Client(timeout=httpx.Timeout(float(timeout_seconds)))

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self.client.request(method, self.base_url + path, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise KdgChainError(f"知行图服务不可达:{exc}") from exc

    @staticmethod
    def _error(resp: httpx.Response, what: str) -> KdgChainError:
        detail = resp.text.strip()
        try:
            detail = resp.json().get("error") or detail
        except ValueError:
            pass
        return KdgChainError(f"{what}失败(HTTP {resp.status_code}):{detail[:300]}")

    def put_body(self, sha256: str, body: bytes) -> str:
        resp = self._request("PUT", f"/bodies/{sha256}", content=body,
                             headers={**self._auth(), "Content-Type": "text/markdown; charset=utf-8"})
        if resp.status_code not in (200, 201):
            raise self._error(resp, "上传正文")
        return f"{self.base_url}/bodies/{sha256}"

    def lookup_member(self, pubkey: str) -> dict | None:
        resp = self._request("GET", "/lookup", params={"pubkey": pubkey})
        if resp.status_code != 200:
            raise self._error(resp, "查询成员")
        data = resp.json()
        return {"account": int(data["account"]), "established": bool(data.get("established"))} if data.get("found") else None

    def lookup_body(self, sha256: str) -> dict | None:
        resp = self._request("GET", "/lookup", params={"body": sha256})
        if resp.status_code != 200:
            raise self._error(resp, "查询正文")
        data = resp.json()
        if not data.get("found"):
            return None
        return {"unit": int(data["unit"]), "versions": [int(v) for v in data.get("versions") or [data["version"]]]}

    def get_unit(self, unit_id: int) -> dict | None:
        resp = self._request("GET", f"/rpc/unit/{int(unit_id)}", headers={"Accept": "application/json"})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise self._error(resp, "读取单元")
        return resp.json()

    def get_nonce(self, account: int) -> int:
        resp = self._request("GET", f"/rpc/account/{int(account)}", headers={"Accept": "application/json"})
        if resp.status_code != 200:
            raise self._error(resp, "读取账户")
        return int(resp.json().get("nonce") or 0)

    def submit_op(self, signed: bytes, *, intent: dict | None = None) -> str:
        resp = self._request("POST", "/rpc/knowledge", content=signed,
                             headers={**self._auth(), "Content-Type": "application/octet-stream", "Accept": "application/json"})
        if resp.status_code != 200:
            raise self._error(resp, "提交到链")
        return str(resp.json().get("hash") or "")

    def unit_url(self, unit_id: int) -> str:
        return f"{self.base_url}/#unit/{int(unit_id)}"

    def list_domains(self) -> list[dict]:
        # 领域只在知行图的领域概念方案里定义(链上只有编号)
        resp = self._request("GET", "/id/domain", headers={"Accept": "application/ld+json"})
        if resp.status_code != 200:
            raise self._error(resp, "读取领域")
        return _domains_from_scheme(resp.json())


@dataclass
class MockKdgChain:
    """测试用的内存链:按真实链的规则接受 create / publish(序号必须对、只有成员能写、正文不能被两个单元共用)。"""

    members: dict[str, int] = field(default_factory=dict)          # 公钥 → 账户号
    established: dict[int, bool] = field(default_factory=dict)
    nonces: dict[int, int] = field(default_factory=dict)
    units: dict[int, dict] = field(default_factory=dict)
    bodies: dict[str, bytes] = field(default_factory=dict)
    submitted: list[bytes] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_member(self, pubkey: str, *, established: bool = True) -> int:
        account = len(self.members) + 1
        self.members[pubkey.lower()] = account
        self.established[account] = established
        self.nonces[account] = 0
        return account

    def put_body(self, sha256: str, body: bytes) -> str:
        if hashlib.sha256(body).hexdigest() != sha256:
            raise KdgChainError("上传正文失败(HTTP 422):哈希与内容不符")
        self.bodies[sha256] = body
        return f"mock://kdg/bodies/{sha256}"

    def lookup_member(self, pubkey: str) -> dict | None:
        account = self.members.get(pubkey.lower())
        return None if account is None else {"account": account, "established": self.established[account]}

    def lookup_body(self, sha256: str) -> dict | None:
        for unit_id, unit in self.units.items():
            versions = [v["n"] for v in unit["versions"] if any(b["hash"] == sha256 for b in v["bodies"])]
            if versions:
                return {"unit": unit_id, "versions": versions}
        return None

    def get_unit(self, unit_id: int) -> dict | None:
        return self.units.get(int(unit_id))

    def get_nonce(self, account: int) -> int:
        return self.nonces.get(int(account), 0)

    def submit_op(self, signed: bytes, *, intent: dict | None = None) -> str:
        if intent is None:
            raise KdgChainError("mock chain needs the intent")
        with self.lock:
            actor, nonce, action = int(intent["actor"]), int(intent["nonce"]), intent["action"]
            if actor not in self.nonces:
                raise KdgChainError("提交到链失败(HTTP 422):account is not a member")
            if nonce != self.nonces[actor]:
                raise KdgChainError("提交到链失败(HTTP 422):bad nonce")
            for body in action.get("bodies") or []:
                if body["hash"] not in self.bodies:
                    raise KdgChainError("提交到链失败(HTTP 422):body not in store")
                owner = self.lookup_body(body["hash"])
                if owner and (action["type"] == "create" or owner["unit"] != int(action.get("unit", 0))):
                    raise KdgChainError("提交到链失败(HTTP 422):body already used by another unit")
            version = {"n": 1, "publisher": actor, "bodies": action.get("bodies") or [], "source": action.get("source"),
                       "cites": action.get("cites") or []}
            if action["type"] == "create":
                unit_id = len(self.units) + 1
                self.units[unit_id] = {"id": unit_id, "layer": action["layer"], "domain": action["domain"], "author": actor,
                                       "versions": [version]}
            elif action["type"] == "publish":
                unit = self.units.get(int(action["unit"]))
                if unit is None:
                    raise KdgChainError("提交到链失败(HTTP 422):unit does not exist")
                version["n"] = len(unit["versions"]) + 1
                unit["versions"].append(version)
            else:
                raise KdgChainError("提交到链失败(HTTP 422):unsupported action")
            self.nonces[actor] += 1
            self.submitted.append(signed)
            return hashlib.sha256(signed).hexdigest()

    def unit_url(self, unit_id: int) -> str:
        return f"mock://kdg/#unit/{int(unit_id)}"

    def list_domains(self) -> list[dict]:
        return [{"id": 1, "name_zh": "大模型应用开发", "name_en": "LLM application development"},
                {"id": 2, "name_zh": "运动健身", "name_en": "Exercise and fitness"}]


_MOCK_CHAIN: MockKdgChain | None = None


def mock_chain() -> MockKdgChain:
    """进程内共享的内存链(测试用)。"""
    global _MOCK_CHAIN
    if _MOCK_CHAIN is None:
        _MOCK_CHAIN = MockKdgChain()
    return _MOCK_CHAIN


def reset_mock_chain() -> MockKdgChain:
    global _MOCK_CHAIN
    _MOCK_CHAIN = MockKdgChain()
    return _MOCK_CHAIN


_LIVE: tuple[tuple, LiveKdgChain] | None = None


def build_kdg_chain() -> KdgChainPort | None:
    """按配置返回适配器;disabled 时返回 None(功能不开放)。

    live 适配器按配置复用同一个实例(同一个 httpx 连接池):每个请求新建客户端而不关闭会泄漏连接。
    """
    global _LIVE
    settings = get_settings()
    if settings.kdg_mode == "live":
        key = (settings.kdg_base_url, settings.kdg_write_token, settings.kdg_timeout_seconds)
        if _LIVE is None or _LIVE[0] != key:
            if _LIVE is not None:
                _LIVE[1].client.close()
            _LIVE = (key, LiveKdgChain(settings.kdg_base_url, settings.kdg_write_token, timeout_seconds=settings.kdg_timeout_seconds))
        return _LIVE[1]
    if settings.kdg_mode == "mock":
        return mock_chain()
    return None
