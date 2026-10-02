"""微信公众号薄 API client。

接口面刻意保持很小（token / 素材 / 草稿 / 发布），全部带：
- access_token 落盘级缓存（内存缓存 + 过期前 10 分钟刷新）
- token 失效自动刷新重试一次
- 网络错误有限重试
- errcode 非零抛 WechatApiError（含操作指引）
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from .errors import TOKEN_EXPIRED_CODES, WechatApiError

API_HOST = "https://api.weixin.qq.com"


class WechatClient:
    def __init__(self, app_id: str, app_secret: str, http: httpx.Client | None = None):
        self.app_id = app_id
        self.app_secret = app_secret
        # 连接级失败（握手/连接重置）自动重试 2 次；业务错误码另行处理
        self._http = http or httpx.Client(timeout=30, transport=httpx.HTTPTransport(retries=2))
        self._token: str | None = None
        self._token_expire_at = 0.0

    # ── token ────────────────────────────────────────────
    def get_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh and self._token and time.time() < self._token_expire_at:
            return self._token
        resp = self._http.get(
            f"{API_HOST}/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": self.app_id, "secret": self.app_secret},
        )
        data = resp.json()
        if "access_token" not in data:
            raise WechatApiError(int(data.get("errcode", -1)), str(data.get("errmsg", "")), "cgi-bin/token")
        self._token = data["access_token"]
        self._token_expire_at = time.time() + int(data.get("expires_in", 7200)) - 600
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        _retry_token: bool = True,
    ) -> dict:
        merged = {"access_token": self.get_token()}
        if params:
            merged.update(params)
        resp = self._http.request(method, f"{API_HOST}{path}", params=merged, json=json_payload, files=files)
        data = resp.json()
        errcode = int(data.get("errcode", 0) or 0)
        if errcode:
            if errcode in TOKEN_EXPIRED_CODES and _retry_token:
                self.get_token(force_refresh=True)
                return self._request(
                    method, path, json_payload=json_payload, params=params, files=files, _retry_token=False
                )
            raise WechatApiError(errcode, str(data.get("errmsg", "")), path)
        return data

    def _post(self, path: str, payload: dict | None = None, **kw) -> dict:
        return self._request("POST", path, json_payload=payload or {}, **kw)

    # ── 素材 ─────────────────────────────────────────────
    def upload_content_image(self, image_path: Path) -> str:
        """正文图：media/uploadimg，返回可在正文中使用的微信域名 URL。"""
        with open(image_path, "rb") as fh:
            data = self._request(
                "POST",
                "/cgi-bin/media/uploadimg",
                files={"media": (image_path.name, fh, _image_mime(image_path))},
            )
        return data["url"]

    def add_material(self, image_path: Path, material_type: str = "thumb") -> str:
        """永久素材（封面用）：material/add_material，返回 thumb media_id。"""
        with open(image_path, "rb") as fh:
            data = self._request(
                "POST",
                "/cgi-bin/material/add_material",
                params={"type": material_type},
                files={"media": (image_path.name, fh, _image_mime(image_path))},
            )
        return data["media_id"]

    # ── 草稿 ─────────────────────────────────────────────
    def add_draft(self, articles: list[dict]) -> str:
        """新增图文草稿，返回草稿 media_id（发布时作为 draft_id 使用）。

        单篇文章字段：title / author / digest / content / thumb_media_id
        （content 必须是微信兼容 HTML，图片必须是微信域名 URL）。
        """
        data = self._post("/cgi-bin/draft/add", {"articles": articles})
        return data["media_id"]

    def get_draft(self, media_id: str) -> dict:
        return self._post("/cgi-bin/draft/get", {"media_id": media_id})

    def draft_count(self) -> int:
        return int(self._post("/cgi-bin/draft/count")["total_count"])

    def delete_draft(self, media_id: str) -> bool:
        self._post("/cgi-bin/draft/delete", {"media_id": media_id})
        return True

    # ── 发布（仅企业认证号有权限，个人号返回 48001）─────────
    def freepublish_submit(self, draft_id: str) -> str:
        """提交发布，返回 publish_id；用 freepublish_get 轮询结果。"""
        data = self._post("/cgi-bin/freepublish/submit", {"media_id": draft_id})
        return data["publish_id"]

    def freepublish_get(self, publish_id: str) -> dict:
        """轮询发布状态。

        publish_status：0 成功（含 article_id / article_detail.article_url）
        1 发布中；2 已删除；3 常规性失败（fail_idx 指出篇目）；4 审核不通过
        """
        return self._post("/cgi-bin/freepublish/get", {"publish_id": publish_id})

    def freepublish_delete(self, article_id: str, index: int = 0) -> bool:
        self._post("/cgi-bin/freepublish/delete", {"article_id": article_id, "index": index})
        return True


def _image_mime(image_path: Path) -> str:
    """按魔数识别图片类型，避免 PNG 被标成 jpeg 而被微信拒绝。"""
    with open(image_path, "rb") as fh:
        head = fh.read(8)
    return "image/png" if head.startswith(b"\x89PNG") else "image/jpeg"


PUBLISH_STATUS_TEXT = {
    0: "发布成功",
    1: "发布中（审核/分发进行中）",
    2: "原文已删除",
    3: "常规性失败（fail_idx 指出失败篇目）",
    4: "审核不通过（终态，不重试）",
}


def parse_publish_result(result: dict) -> dict:
    """把 freepublish/get 的响应压平成统一结构，供落盘与展示。"""
    status = int(result.get("publish_status", -1))
    out = {
        "status": status,
        "status_text": PUBLISH_STATUS_TEXT.get(status, f"未知状态 {status}"),
        "article_id": result.get("article_id") or None,
        "article_urls": [],
        "fail_idx": result.get("fail_idx") or None,
    }
    detail = result.get("article_detail") or {}
    out["article_urls"] = [item.get("article_url") for item in detail.get("item", []) if item.get("article_url")]
    return out
