"""LLM 封装：任意 OpenAI 兼容端点，参数全部来自配置。

支持按环节覆盖（config 的 [llm.writer] 等）；JSON 输出为尽力而为——
先尝试 response_format=json_object，供应商不支持时退回普通调用再从
回复中提取 JSON（剥掉 ```json 围栏等噪音）。
"""

from __future__ import annotations

import json
import re
import time

from openai import OpenAI

from .config import Config, LLMConfig


class LLMError(Exception):
    pass


class LLM:
    def __init__(self, cfg: Config, stage: str | None = None):
        self.stage = stage or ""
        eff: LLMConfig = cfg.llm.stage(stage) if stage else cfg.llm
        self.effective = eff
        self.client = OpenAI(
            base_url=eff.base_url,
            api_key=cfg.resolve_llm_key(eff),
            timeout=eff.timeout_sec,
            max_retries=2,
        )
        self.usage_tokens = 0

    def chat(self, system: str, user: str, *, json_mode: bool = False, temperature: float | None = None) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kwargs: dict = {
            "model": self.effective.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.effective.temperature,
            "max_tokens": self.effective.max_tokens,
        }
        try:
            if json_mode:
                resp = self.client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
            else:
                resp = self.client.chat.completions.create(**kwargs)
        except Exception:
            if not json_mode:
                raise
            resp = self.client.chat.completions.create(**kwargs)

        if resp.usage:
            self.usage_tokens += resp.usage.total_tokens
        content = resp.choices[0].message.content
        if not content or not content.strip():
            raise LLMError(f"[{self.stage}] 模型返回了空内容")
        return content.strip()

    def chat_json(self, system: str, user: str) -> dict:
        """要求 JSON 输出并解析；解析失败把错误喂回去重试一次。"""
        reply = self.chat(system, user, json_mode=True)
        parsed = _extract_json(reply)
        if parsed is not None:
            return parsed
        retry = self.chat(
            system,
            user + "\n\n【重要】只输出一个合法的 JSON 对象，不要任何解释文字或代码围栏。"
            f"你上一次的回复无法解析为 JSON：{_json_error(reply)}",
            json_mode=True,
        )
        parsed = _extract_json(retry)
        if parsed is None:
            raise LLMError(f"[{self.stage}] 两次都无法解析出 JSON，最后回复片段：{retry[:200]}")
        return parsed

    def ping(self) -> str:
        """连通性探测：一次最小调用。"""
        return self.chat("你是回声服务，只回复用户原话。", "ping")


def _json_error(text: str) -> str:
    try:
        json.loads(_strip_fence(text))
        return ""
    except Exception as err:
        return str(err)[:120]


def _strip_fence(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, re.DOTALL)
    return fence.group(1) if fence else text


def _extract_json(reply: str) -> dict | None:
    text = _strip_fence(reply)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None


class UsageTracker:
    """汇总一次 run 的各环节 token 用量。"""

    def __init__(self):
        self.started = time.time()
        self.by_stage: dict[str, int] = {}

    def record(self, stage: str, llm: LLM) -> None:
        self.by_stage[stage] = self.by_stage.get(stage, 0) + llm.usage_tokens

    def summary(self) -> dict:
        return {
            "total_tokens": sum(self.by_stage.values()),
            "by_stage": dict(self.by_stage),
            "elapsed_sec": round(time.time() - self.started, 1),
        }
