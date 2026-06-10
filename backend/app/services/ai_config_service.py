"""
AI 运行时配置服务 — Phase 19.2

配置来源优先级：
1. 运行时配置文件 backend/app/data/ai_runtime_config.json
2. .env / 环境变量（通过 settings）
3. 默认 mock

注意：不保存 DASHSCOPE_API_KEY，API Key 只从环境变量读取。
"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "data")
CONFIG_FILE = os.path.join(CONFIG_DIR, "ai_runtime_config.json")

DEFAULT_CONFIG = {
    "provider": "mock",
    "model": "mock-v1.0",
    "prompt_version": "labelhub_qa_quality_v1",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "timeout_seconds": 25,
    "mock_fallback": True,
    "force_json": True,
    "updated_at": None,
    "updated_by": "system"
}

ALLOWED_PROVIDERS = {"mock", "dashscope"}
DASHSCOPE_MODELS = {"qwen3.7-plus", "qwen-plus", "qwen-turbo", "qwen-max", "qwen3.6-plus", "qwen3-plus", "qwen3-turbo"}


def _ensure_config_dir() -> None:
    """确保配置目录存在。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _read_config_file() -> Optional[Dict[str, Any]]:
    """从文件读取配置，失败返回 None。"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning(f"[ai_config] Failed to read config file: {e}")
    return None


def _write_config_file(config: Dict[str, Any]) -> None:
    """写入配置文件。"""
    _ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except (IOError, OSError) as e:
        logger.error(f"[ai_config] Failed to write config file: {e}")


def _is_api_key_present() -> bool:
    """检查当前 provider 对应的 API Key 是否已配置。"""
    config = get_runtime_config()
    provider = config.get("provider", "mock")
    if provider == "mock":
        return False
    if provider == "dashscope":
        return bool(settings.DASHSCOPE_API_KEY or settings.LLM_API_KEY)
    return bool(settings.LLM_API_KEY)


def get_runtime_config() -> Dict[str, Any]:
    """获取当前运行时配置。

    优先级：运行时配置文件 > .env/环境变量 > 默认 mock
    """
    # 1. 尝试读取运行时配置文件
    file_config = _read_config_file()
    if file_config and isinstance(file_config, dict) and "provider" in file_config:
        return file_config

    # 2. 从环境变量构建配置
    env_provider = settings.AI_PROVIDER.lower().strip()
    if env_provider in ("qwen", "dashscope"):
        env_config = {
            "provider": "dashscope",
            "model": settings.DASHSCOPE_MODEL or settings.AI_MODEL_NAME or "qwen3.7-plus",
            "prompt_version": "labelhub_qa_quality_v1",
            "base_url": settings.DASHSCOPE_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "timeout_seconds": settings.AI_TIMEOUT_SECONDS or 25,
            "mock_fallback": settings.AI_MOCK_FALLBACK,
            "force_json": settings.AI_FORCE_JSON,
            "updated_at": None,
            "updated_by": "env"
        }
        return env_config

    # 3. 默认 mock
    return dict(DEFAULT_CONFIG)


def get_effective_config() -> Dict[str, Any]:
    """获取生效配置，包含 api_key_present 和 effective_provider/model。"""
    config = get_runtime_config()
    provider = config.get("provider", "mock")
    api_key_present = _is_api_key_present()

    # 如果 provider=dashscope 但没有 API Key，effective 回退到 mock
    effective_provider = provider
    effective_model = config.get("model", "mock-v1.0")
    if provider != "mock" and not api_key_present:
        # 不自动回退，只是标记；实际回退在 ai_provider 中处理
        pass

    return {
        "provider": provider,
        "model": config.get("model", "mock-v1.0"),
        "base_url": config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "prompt_version": config.get("prompt_version", "labelhub_qa_quality_v1"),
        "timeout_seconds": config.get("timeout_seconds", 25),
        "mock_fallback": config.get("mock_fallback", True),
        "force_json": config.get("force_json", True),
        "api_key_present": api_key_present,
        "effective_provider": effective_provider,
        "effective_model": effective_model,
        "updated_at": config.get("updated_at"),
        "updated_by": config.get("updated_by", "system")
    }


def update_runtime_config(updates: Dict[str, Any], updated_by: str = "owner") -> Dict[str, Any]:
    """更新运行时配置。

    不保存 API Key。只保存 provider/model/base_url/timeout/fallback/force_json。
    """
    current = get_runtime_config()

    # 验证 provider
    provider = updates.get("provider", current.get("provider", "mock"))
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"Invalid provider: {provider}. Allowed: {ALLOWED_PROVIDERS}")

    # 验证 model
    model = updates.get("model", current.get("model", "mock-v1.0"))
    if not model or not isinstance(model, str):
        raise ValueError("model cannot be empty")

    # 如果 provider=mock，强制 model=mock-v1.0
    if provider == "mock":
        model = "mock-v1.0"

    # 构建新配置
    new_config = {
        "provider": provider,
        "model": model,
        "prompt_version": updates.get("prompt_version", current.get("prompt_version", "labelhub_qa_quality_v1")),
        "base_url": updates.get("base_url", current.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
        "timeout_seconds": updates.get("timeout_seconds", current.get("timeout_seconds", 25)),
        "mock_fallback": updates.get("mock_fallback", current.get("mock_fallback", True)),
        "force_json": updates.get("force_json", current.get("force_json", True)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": updated_by
    }

    _write_config_file(new_config)

    logger.info(f"[ai_config] Config updated: provider={provider}, model={model}, by={updated_by}")

    # 检查 API Key 状态
    warning = None
    if provider == "dashscope" and not _is_api_key_present():
        warning = "DASHSCOPE_API_KEY 未配置，真实调用会失败并 fallback"

    result = get_effective_config()
    if warning:
        result["warning"] = warning

    return result
