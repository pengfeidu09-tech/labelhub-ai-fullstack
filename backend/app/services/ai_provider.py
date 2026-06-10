import json
import re
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

import requests

from app.core.config import settings
from app.services.ai_config_service import get_runtime_config

logger = logging.getLogger(__name__)


def _sanitize_key_for_log(api_key: str) -> Dict[str, Any]:
    """返回脱敏后的 API Key 信息，用于日志。绝不返回完整 key。"""
    if not api_key:
        return {"api_key_present": False, "api_key_length": 0, "api_key_prefix": ""}
    return {
        "api_key_present": True,
        "api_key_length": len(api_key),
        "api_key_prefix": api_key[:4],
    }


def classify_error(exc: Exception, response=None) -> Tuple[str, str]:
    """根据异常或 HTTP 响应分类错误。

    Returns:
        (error_type, error_message_short)
    """
    # 优先按 HTTP 状态码分类
    if response is not None:
        status = getattr(response, "status_code", None)
        if status == 401:
            return ("invalid_api_key", "API Key 无效或未授权 (HTTP 401)")
        if status == 403:
            return ("forbidden", "API 拒绝访问 (HTTP 403)")
        if status == 404:
            return ("endpoint_not_found", "API endpoint 不存在 (HTTP 404)")
        if status == 400:
            return ("bad_request", f"请求参数错误 (HTTP 400): {(getattr(response, 'text', '') or '')[:200]}")
        if status == 429:
            return ("rate_limited", "API 限流 (HTTP 429)")
        if status and 500 <= status < 600:
            return ("server_error", f"API 服务器错误 (HTTP {status})")
        if status and status != 200:
            text = (getattr(response, "text", "") or "")[:200]
            return ("http_error", f"HTTP {status}: {text}")

    # 网络 / 客户端异常
    if isinstance(exc, requests.exceptions.Timeout):
        return ("timeout", "请求超时")
    if isinstance(exc, requests.exceptions.ConnectionError):
        return ("network_error", f"网络连接错误: {str(exc)[:200]}")
    if isinstance(exc, requests.exceptions.SSLError):
        return ("ssl_error", f"SSL 错误: {str(exc)[:200]}")
    if isinstance(exc, requests.exceptions.RequestException):
        return ("network_error", f"网络错误: {str(exc)[:200]}")

    msg = str(exc) or ""
    low = msg.lower()
    if "timeout" in low or "timed out" in low:
        return ("timeout", f"请求超时: {msg[:200]}")
    if "json" in low and ("parse" in low or "decode" in low or "expecting" in low):
        return ("json_parse_error", f"JSON 解析失败: {msg[:200]}")
    if "connection" in low or "refused" in low or "unreachable" in low or "dns" in low:
        return ("network_error", f"网络错误: {msg[:200]}")
    if "ssl" in low or "certificate" in low:
        return ("ssl_error", f"SSL 错误: {msg[:200]}")

    return ("unknown_error", msg[:200] or exc.__class__.__name__)


def _extract_json_object(text: str) -> Optional[Dict]:
    """从 LLM 输出中尝试解析 JSON 对象，支持 markdown 代码块。"""
    if not text:
        return None
    text = text.strip()

    # 1. 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. 提取 markdown ```json ... ``` 代码块
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if md_match:
        inner = md_match.group(1).strip()
        try:
            obj = json.loads(inner)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. 提取第一个 { ... } 顶层对象（平衡花括号）
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except (json.JSONDecodeError, TypeError):
                        start = None
                        continue
    return None


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    def get_base_url(self) -> str:
        return ""

    def get_api_key(self) -> str:
        return ""

    def get_request_url(self) -> str:
        base = self.get_base_url().rstrip("/")
        if base:
            return f"{base}/chat/completions"
        return ""

    def test_connection(self) -> Dict[str, Any]:
        """测试 provider 连接是否正常。子类可覆写。"""
        return {
            "provider": self.get_provider_name(),
            "model": self.get_model_name(),
            "base_url": self.get_base_url(),
            "api_key_present": bool(self.get_api_key()),
            "api_key_length": len(self.get_api_key() or ""),
            "request_url": self.get_request_url(),
            "test_status": "skipped",
            "http_status": None,
            "error_type": None,
            "error_message": None,
            "raw_response_preview": "",
            "latency_ms": 0,
            "fallback_available": bool(
                get_runtime_config().get("mock_fallback", True)
            ),
        }


class MockProvider(AIProvider):
    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return "mock-v1.0"

    def get_base_url(self) -> str:
        return ""

    def get_api_key(self) -> str:
        return ""

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        return {
            "raw_text": "[Mock AI Response] Based on analysis of the provided data.",
            "parsed": None,
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "latency_ms": 50,
            "error_type": None,
            "error_message": None,
            "http_status": 200,
        }

    def test_connection(self) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model": "mock-v1.0",
            "base_url": "",
            "api_key_present": False,
            "api_key_length": 0,
            "request_url": "",
            "test_status": "success",
            "http_status": None,
            "error_type": None,
            "error_message": None,
            "raw_response_preview": "",
            "latency_ms": 0,
            "fallback_available": bool(
                get_runtime_config().get("mock_fallback", True)
            ),
        }


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        provider_name: str,
        model_name: str,
        api_key: str,
        base_url: str,
        timeout: int = 25,
    ):
        self._provider_name = provider_name
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get_provider_name(self) -> str:
        return self._provider_name

    def get_model_name(self) -> str:
        return self._model_name

    def get_base_url(self) -> str:
        return self._base_url

    def get_api_key(self) -> str:
        return self._api_key

    def _build_request_body(self, messages: list) -> Dict[str, Any]:
        """构造请求体。

        注意：DashScope 的 OpenAI 兼容模式不支持 response_format / json_schema，
        JSON 输出依赖 prompt 中的 system 指令约束。
        """
        body = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0.1,
        }
        # 即便 settings.AI_FORCE_JSON=true 也不下发 response_format，
        # 避免 DashScope 兼容接口返回 400。
        return body

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        start = time.time()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_body = self._build_request_body(messages)
        url = f"{self._base_url}/chat/completions"
        key_info = _sanitize_key_for_log(self._api_key)

        try:
            logger.info(
                f"[ai_provider] POST {url} provider={self._provider_name} model={self._model_name} "
                f"timeout={self._timeout}s key={key_info}"
            )
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=self._timeout,
            )
            latency_ms = int((time.time() - start) * 1000)
            http_status = resp.status_code

            if http_status != 200:
                error_text = (resp.text or "")[:500]
                err_type, err_msg = classify_error(None, resp)
                logger.error(
                    f"[ai_provider] {self._provider_name}/{self._model_name} HTTP {http_status} "
                    f"in {latency_ms}ms err_type={err_type} body={error_text[:300]}"
                )
                return {
                    "raw_text": "",
                    "parsed": None,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "latency_ms": latency_ms,
                    "error_type": err_type,
                    "error_message": f"HTTP {http_status}: {error_text[:300]}",
                    "http_status": http_status,
                }

            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError) as json_err:
                preview = (resp.text or "")[:500]
                logger.error(
                    f"[ai_provider] {self._provider_name}/{self._model_name} invalid JSON response: {json_err}"
                )
                return {
                    "raw_text": preview,
                    "parsed": None,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "latency_ms": latency_ms,
                    "error_type": "json_parse_error",
                    "error_message": f"响应不是合法 JSON: {str(json_err)[:200]} | body前500字符={preview[:500]}",
                    "http_status": http_status,
                }

            try:
                raw_text = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError) as e:
                preview = json.dumps(data, ensure_ascii=False)[:500]
                logger.error(
                    f"[ai_provider] {self._provider_name}/{self._model_name} unexpected response shape: {e}"
                )
                return {
                    "raw_text": preview,
                    "parsed": None,
                    "token_usage": data.get("usage", {}) if isinstance(data, dict) else {},
                    "latency_ms": latency_ms,
                    "error_type": "invalid_response_shape",
                    "error_message": f"响应结构异常: {str(e)[:200]} | body={preview[:500]}",
                    "http_status": http_status,
                }

            usage = data.get("usage", {}) if isinstance(data, dict) else {}

            parsed = _extract_json_object(raw_text)
            if parsed is None and raw_text:
                logger.warning(
                    f"[ai_provider] {self._provider_name}/{self._model_name} JSON parse failed, "
                    f"raw_preview={raw_text[:200]}"
                )

            logger.info(
                f"[ai_provider] {self._provider_name}/{self._model_name} HTTP {http_status} "
                f"in {latency_ms}ms parsed={parsed is not None} raw_len={len(raw_text)}"
            )

            return {
                "raw_text": raw_text,
                "parsed": parsed,
                "token_usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                "latency_ms": latency_ms,
                "error_type": None,
                "error_message": None,
                "http_status": http_status,
            }
        except requests.exceptions.Timeout as e:
            latency_ms = int((time.time() - start) * 1000)
            err_type, err_msg = classify_error(e, None)
            logger.error(
                f"[ai_provider] {self._provider_name}/{self._model_name} timeout after {self._timeout}s "
                f"in {latency_ms}ms err_type={err_type}"
            )
            return {
                "raw_text": "",
                "parsed": None,
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "latency_ms": latency_ms,
                "error_type": err_type,
                "error_message": f"请求超时 ({self._timeout}s)",
                "http_status": None,
            }
        except requests.exceptions.RequestException as e:
            latency_ms = int((time.time() - start) * 1000)
            err_type, err_msg = classify_error(e, None)
            logger.error(
                f"[ai_provider] {self._provider_name}/{self._model_name} request error "
                f"in {latency_ms}ms err_type={err_type} msg={str(e)[:200]}"
            )
            return {
                "raw_text": "",
                "parsed": None,
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "latency_ms": latency_ms,
                "error_type": err_type,
                "error_message": str(e)[:300] or err_msg,
                "http_status": None,
            }
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            err_type, err_msg = classify_error(e, None)
            logger.error(
                f"[ai_provider] {self._provider_name}/{self._model_name} unexpected error "
                f"in {latency_ms}ms err_type={err_type} msg={str(e)[:200]}"
            )
            return {
                "raw_text": "",
                "parsed": None,
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "latency_ms": latency_ms,
                "error_type": err_type,
                "error_message": str(e)[:300] or err_msg,
                "http_status": None,
            }

    def test_connection(self) -> Dict[str, Any]:
        """测试 Provider 连接是否正常。失败时返回真实错误，不 fallback 到 mock。"""
        runtime = get_runtime_config()
        fallback_available = bool(runtime.get("mock_fallback", True))

        result: Dict[str, Any] = {
            "provider": self._provider_name,
            "model": self._model_name,
            "base_url": self._base_url,
            "api_key_present": bool(self._api_key),
            "api_key_length": len(self._api_key or ""),
            "request_url": f"{self._base_url}/chat/completions",
            "test_status": "failed",
            "http_status": None,
            "error_type": None,
            "error_message": None,
            "raw_response_preview": "",
            "latency_ms": 0,
            "fallback_available": fallback_available,
        }

        if not self._api_key:
            result["error_type"] = "missing_api_key"
            result["error_message"] = "API Key 未配置 (DASHSCOPE_API_KEY / LLM_API_KEY 为空)"
            return result

        key_info = _sanitize_key_for_log(self._api_key)
        logger.info(
            f"[provider-test] POST {result['request_url']} provider={self._provider_name} "
            f"model={self._model_name} key={key_info}"
        )

        start = time.time()
        try:
            resp = requests.post(
                result["request_url"],
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "temperature": 0.0,
                    "max_tokens": 8,
                },
                timeout=10,
            )
            result["latency_ms"] = int((time.time() - start) * 1000)
            result["http_status"] = resp.status_code
            result["raw_response_preview"] = (resp.text or "")[:500]

            if resp.status_code == 200:
                result["test_status"] = "success"
                return result

            err_type, _ = classify_error(None, resp)
            result["error_type"] = err_type
            if resp.status_code == 400:
                # 400 常常是 model not found 或参数错误
                snippet = (resp.text or "")[:200]
                if "model" in snippet.lower() and ("not" in snippet.lower() or "invalid" in snippet.lower()):
                    result["error_type"] = "model_not_found"
                result["error_message"] = f"HTTP {resp.status_code}: {snippet}"
            else:
                result["error_message"] = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
            return result
        except requests.exceptions.Timeout as e:
            result["latency_ms"] = int((time.time() - start) * 1000)
            err_type, _ = classify_error(e, None)
            result["error_type"] = err_type
            result["error_message"] = f"请求超时 (10s): {str(e)[:200]}"
            return result
        except requests.exceptions.RequestException as e:
            result["latency_ms"] = int((time.time() - start) * 1000)
            err_type, _ = classify_error(e, None)
            result["error_type"] = err_type
            result["error_message"] = f"网络错误: {str(e)[:200]}"
            return result
        except Exception as e:
            result["latency_ms"] = int((time.time() - start) * 1000)
            err_type, _ = classify_error(e, None)
            result["error_type"] = err_type
            result["error_message"] = f"未知错误: {str(e)[:200]}"
            return result


def get_ai_provider() -> AIProvider:
    """每次调用时从运行时配置读取当前 provider 设置。

    配置来源优先级：
    1. ai_runtime_config.json（运行时可修改）
    2. .env / 环境变量
    3. 默认 mock
    """
    config = get_runtime_config()
    provider = config.get("provider", "mock").lower().strip()

    if provider == "mock":
        return MockProvider()

    # DashScope / Qwen via compatible-mode API
    if provider in ("qwen", "dashscope"):
        api_key = settings.DASHSCOPE_API_KEY or settings.LLM_API_KEY
        model_name = (
            config.get("model")
            or settings.DASHSCOPE_MODEL
            or settings.AI_MODEL_NAME
            or "qwen3.7-plus"
        )
        base_url = (
            config.get("base_url")
            or settings.DASHSCOPE_BASE_URL
            or settings.LLM_API_BASE_URL
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        timeout = config.get("timeout_seconds") or settings.AI_TIMEOUT_SECONDS or 25
        # 即便没有 api_key，也返回真实 provider 实例，由调用方决定是否 fallback
        return OpenAICompatibleProvider(
            provider_name="dashscope",
            model_name=model_name,
            api_key=api_key or "",
            base_url=base_url,
            timeout=timeout,
        )

    # Generic OpenAI-compatible providers
    api_key = settings.LLM_API_KEY
    model_name = config.get("model") or settings.AI_MODEL_NAME or "unknown"
    base_url = (
        config.get("base_url")
        or settings.LLM_API_BASE_URL
        or "https://api.openai.com/v1"
    )
    if provider == "deepseek":
        base_url = base_url or "https://api.deepseek.com/v1"
    elif provider == "openai":
        base_url = base_url or "https://api.openai.com/v1"
    timeout = config.get("timeout_seconds") or settings.AI_TIMEOUT_SECONDS or 25

    return OpenAICompatibleProvider(
        provider_name=provider,
        model_name=model_name,
        api_key=api_key or "",
        base_url=base_url,
        timeout=timeout,
    )
