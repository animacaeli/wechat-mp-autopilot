"""微信错误码解释与处理策略。

微信侧报错以 errcode/errmsg 返回；这里把常见错误码翻译成
「是什么 + 去哪修」的操作指引，避免用户面对裸错误码猜谜。
"""

from __future__ import annotations

# errcode -> (含义, 处理建议)
KNOWN_ERRORS: dict[int, tuple[str, str]] = {
    -1: ("系统繁忙", "服务器暂时不可用，稍后重试即可"),
    0: ("成功", ""),
    40001: ("access_token 无效", "通常是缓存过期或 AppSecret 变更；客户端会自动刷新一次，若仍失败请重跑"),
    40007: ("media_id 无效", "素材可能已过期或归属其他账号；流程会自动重传素材一次"),
    40013: ("appid 不合法", "检查 WECHAT_APP_ID 是否填对（后台「设置与开发→基本配置」）"),
    40125: ("AppSecret 无效或已重置", "到后台「基本配置」重置 Secret 后更新 .env 中的 WECHAT_APP_SECRET"),
    40164: ("请求 IP 不在白名单", "到后台「基本配置→IP 白名单」加入本机/服务器出口 IP；错误信息里通常带有具体 IP"),
    41001: ("缺少 access_token 参数", "属于程序内部问题，请提交 issue"),
    42001: ("access_token 已过期", "客户端会自动刷新重试一次"),
    45009: ("接口调用超过限额", "今日额度用尽，明天再跑；或检查是否有失控的定时任务"),
    48001: ("api 功能未授权", "当前账号没有该接口权限：请到后台「设置与开发→接口权限」页核对。"
                          "常见于个人号调用 freepublish（2025.7 起个人号无发布权限）"),
    53400: ("请求过于频繁", "触发频控，稍等后再试"),
    53401: (" secretive content 风控", "内容命中平台风控，请调整内容后重试"),
}

# 这些错误码意味着 token 失效，客户端应刷新 token 后重试一次
TOKEN_EXPIRED_CODES = {40001, 42001}


class WechatApiError(Exception):
    """微信接口返回非零 errcode。guidance 属性给出操作指引。"""

    def __init__(self, errcode: int, errmsg: str, api: str):
        self.errcode = errcode
        self.errmsg = errmsg
        self.api = api
        meaning, action = KNOWN_ERRORS.get(errcode, ("未知错误", "请把 errcode/errmsg 提交 issue"))
        self.guidance = f"{meaning}。{action}"
        super().__init__(f"微信接口 {api} 失败：[{errcode}] {errmsg} — {self.guidance}")
