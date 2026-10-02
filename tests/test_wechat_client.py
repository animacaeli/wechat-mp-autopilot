"""微信薄 client 测试：fixture 驱动（httpx.MockTransport），不发真实请求。

企业发布路径（freepublish/submit + get + delete）作者无企业号可实测，
这里以官方文档响应结构为 fixture 保证代码逻辑正确——待社区实测闭环。
"""

import json

import httpx
import pytest

from autopilot.wechat.client import WechatClient, parse_publish_result
from autopilot.wechat.errors import WechatApiError


def make_client(handler) -> tuple[WechatClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def tracking_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(tracking_handler), timeout=10)
    return WechatClient("appid", "secret", http=http), requests


def ok(payload=None):
    return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", **(payload or {})})


def test_token_cached_across_calls():
    def handler(request):
        if request.url.path == "/cgi-bin/token":
            return ok({"access_token": "T1", "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/count":
            return ok({"total_count": 3})
        raise AssertionError(request.url.path)

    client, requests = make_client(handler)
    assert client.draft_count() == 3
    assert client.draft_count() == 3
    token_calls = [r for r in requests if r.url.path == "/cgi-bin/token"]
    assert len(token_calls) == 1  # 第二次复用缓存


def test_token_error_raises_with_guidance():
    def handler(request):
        return httpx.Response(200, json={"errcode": 40164, "errmsg": "invalid ip 1.2.3.4 ipv6 ::ffff:1.2.3.4"})

    client, _ = make_client(handler)
    with pytest.raises(WechatApiError) as exc_info:
        client.get_token()
    assert "IP" in exc_info.value.guidance


def test_draft_add_returns_media_id():
    def handler(request):
        if request.url.path == "/cgi-bin/draft/add":
            body = json.loads(request.content)
            assert body["articles"][0]["title"] == "标题"
            return ok({"media_id": "DRAFT123"})
        return ok({"access_token": "T1"})

    client, _ = make_client(handler)
    media_id = client.add_draft([{"title": "标题", "content": "<p>x</p>", "digest": "d", "thumb_media_id": "t"}])
    assert media_id == "DRAFT123"


def test_expired_token_triggers_refresh_and_retry():
    state = {"token_calls": 0, "draft_calls": 0}

    def handler(request):
        if request.url.path == "/cgi-bin/token":
            state["token_calls"] += 1
            return ok({"access_token": f"T{state['token_calls']}", "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/count":
            state["draft_calls"] += 1
            if state["draft_calls"] == 1:
                return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential"})
            return ok({"total_count": 0})
        raise AssertionError(request.url.path)

    client, _ = make_client(handler)
    assert client.draft_count() == 0
    assert state["token_calls"] == 2  # 刷新过一次


def test_unauthorized_48001_raises():
    def handler(request):
        if request.url.path == "/cgi-bin/freepublish/submit":
            return httpx.Response(200, json={"errcode": 48001, "errmsg": "api unauthorized"})
        return ok({"access_token": "T1"})

    client, _ = make_client(handler)
    with pytest.raises(WechatApiError) as exc_info:
        client.freepublish_submit("DRAFT123")
    assert exc_info.value.errcode == 48001
    assert "接口权限" in exc_info.value.guidance


# ── freepublish 响应解析（fixture 来自官方文档响应结构）────


def test_parse_publish_success():
    result = parse_publish_result(
        {
            "publish_id": 1,
            "publish_status": 0,
            "article_id": "ART1",
            "article_detail": {"count": 1, "item": [{"article_url": "https://mp.weixin.qq.com/s/abc"}]},
        }
    )
    assert result["status"] == 0
    assert result["article_urls"] == ["https://mp.weixin.qq.com/s/abc"]


def test_parse_publish_in_progress():
    assert parse_publish_result({"publish_id": 1, "publish_status": 1})["status"] == 1


def test_parse_publish_rejected():
    result = parse_publish_result({"publish_id": 1, "publish_status": 4})
    assert result["status"] == 4
    assert "审核不通过" in result["status_text"]


def test_parse_publish_common_fail():
    result = parse_publish_result({"publish_id": 1, "publish_status": 3, "fail_idx": [0]})
    assert result["fail_idx"] == [0]
