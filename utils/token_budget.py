"""
全局 Token 预算追踪模块

提供线程安全的全局 token 消耗追踪和预算限制。
通过 LangChain BaseCallbackHandler 在每次 LLM 调用完成后自动累加 token 用量。
当累计 token 超过配置上限时，API 层会拒绝新的对话请求。

Token 用量会持久化到 JSON 文件，程序重启后自动恢复，避免信息丢失。
默认每增加 save_interval 个 token 时写入一次文件，减少磁盘 I/O。

使用方式:
    # 在 API 入口处检查预算
    from utils.token_budget import check_budget_or_raise
    check_budget_or_raise()  # 超限时抛出 TokenBudgetExceededError

    # 查询当前使用情况
    from utils.token_budget import get_tracker
    tracker = get_tracker()
    print(tracker.get_usage())  # {"total_tokens": 12345, "limit": 1000000, "percent": 1.23}

    # 手动保存（程序退出前调用，防止阈值未触发导致的丢失）
    tracker.force_save()

    # 重置计数器（同时写入文件）
    tracker.reset()
"""
from __future__ import annotations

import json
import os
import threading
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path


logger = logging.getLogger("token_budget")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass
class TokenBudgetConfig:
    """Token 预算配置"""

    enabled: bool = True
    limit: int = 1_000_000
    reject_message: str = "Token budget exceeded. Please try again later."
    http_status: int = 429
    persist_path: str = "output/token_budget.json"
    save_interval: int = 10_000

    @classmethod
    def from_config(cls, config: dict | None = None) -> "TokenBudgetConfig":
        """从配置字典创建实例，缺失字段使用默认值"""
        if config is None:
            config = agent_conf.get("token_budget", {})
        if not isinstance(config, dict):
            config = {}
        return cls(
            enabled=config.get("enabled", True),
            limit=config.get("limit", 1_000_000),
            reject_message=config.get("reject_message", "Token budget exceeded. Please try again later."),
            http_status=config.get("http_status", 429),
            persist_path=config.get("persist_path", "output/token_budget.json"),
            save_interval=config.get("save_interval", 10_000),
        )


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class TokenBudgetExceededError(Exception):
    """全局 token 预算超限异常

    API 层应捕获此异常并返回友好的错误响应。
    """

    def __init__(self, config: TokenBudgetConfig, total_tokens: int) -> None:
        self.http_status = config.http_status
        self.message = config.reject_message
        self.usage = {
            "total_tokens": total_tokens,
            "limit": config.limit,
            "percent": round(total_tokens / config.limit * 100, 2) if config.limit > 0 else 0,
        }
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# 回调处理器
# ---------------------------------------------------------------------------


class TokenBudgetCallbackHandler(BaseCallbackHandler):
    """LangChain 回调处理器：在每次 LLM 调用完成后提取并累加 token 用量"""

    def __init__(self, tracker: "TokenBudgetTracker") -> None:
        super().__init__()
        self._tracker = tracker

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """从 LLMResult 中提取 token 用量并累加到全局计数器"""
        count = self._extract_token_count(response)
        if count > 0:
            self._tracker.add_tokens(count)

    @staticmethod
    def _extract_token_count(response: LLMResult) -> int:
        """从 LLMResult 中提取 token 消耗总数

        支持多种提供商的 token 用量格式：
        - OpenAI / Qwen (DashScope): response.llm_output["token_usage"]["total_tokens"]
        - DeepSeek: response.generations[*][*].generation_info["token_usage"]["total_tokens"]
        """
        # 策略 1: llm_output 中的 token_usage（OpenAI / Qwen 模式）
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if usage and "total_tokens" in usage:
                logger.debug(
                    "[TokenBudget] 从 llm_output.token_usage 提取: "
                    f"total={usage['total_tokens']}, "
                    f"prompt={usage.get('prompt_tokens', '?')}, "
                    f"completion={usage.get('completion_tokens', '?')}"
                )
                return usage["total_tokens"]

        # 策略 2: 遍历 generations[*][*].generation_info["token_usage"]（DeepSeek 模式）
        total = 0
        for gen_list in response.generations:
            for gen in gen_list:
                info = getattr(gen, "generation_info", None) or {}
                if isinstance(info, dict):
                    usage = info.get("token_usage", {})
                    if isinstance(usage, dict) and "total_tokens" in usage:
                        total += usage["total_tokens"]

        if total > 0:
            logger.debug(f"[TokenBudget] 从 generation_info.token_usage 提取: total={total}")

        if total == 0:
            # 静默降级：部分提供商可能不返回 token 用量
            logger.debug(
                "[TokenBudget] 未能从 LLMResult 中提取 token 用量，"
                "将跳过此次累加（这不影响功能）"
            )

        return total


# ---------------------------------------------------------------------------
# 全局追踪器（线程安全单例）
# ---------------------------------------------------------------------------


class TokenBudgetTracker:
    """全局 Token 预算追踪器（线程安全单例）

    在 API 入口处检查预算，在每次 LLM 调用后累加 token 用量。
    Token 用量持久化到 JSON 文件，程序重启后自动恢复。
    """

    _instance: ClassVar[Optional["TokenBudgetTracker"]] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls) -> "TokenBudgetTracker":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._lock = threading.Lock()
                    instance._config = TokenBudgetConfig.from_config()
                    instance._callback = None
                    # 从持久化文件恢复上次的 token 计数
                    instance._total_tokens = instance._load_from_file()
                    instance._last_saved_tokens = instance._total_tokens
                    cls._instance = instance
        return cls._instance

    # -- 配置 --

    @property
    def config(self) -> TokenBudgetConfig:
        return self._config

    def reload_config(self) -> None:
        """重新加载配置（用于运行时更新）"""
        self._config = TokenBudgetConfig.from_config()
        logger.info(
            f"[TokenBudget] 配置已重载: enabled={self._config.enabled}, "
            f"limit={self._config.limit:,}"
        )

    # -- 预算检查 --

    def check_budget(self) -> bool:
        """检查是否在预算内

        Returns:
            True 表示可以继续，False 表示预算已超限
        """
        if not self._config.enabled:
            return True
        with self._lock:
            return self._total_tokens < self._config.limit

    def check_budget_or_raise(self) -> None:
        """检查预算，超限时抛出 TokenBudgetExceededError"""
        if not self._config.enabled:
            return
        with self._lock:
            if self._total_tokens >= self._config.limit:
                raise TokenBudgetExceededError(self._config, self._total_tokens)

    # -- Token 累加 --

    def add_tokens(self, count: int) -> None:
        """累加 token 用量（线程安全）

        在 LLM 调用完成后由回调处理器调用。
        当累计增长量达到 save_interval 时自动持久化到文件。
        """
        if count <= 0:
            return
        with self._lock:
            self._total_tokens += count
            logger.info(
                f"[TokenBudget] +{count:,} tokens → "
                f"累计 {self._total_tokens:,} / {self._config.limit:,} "
                f"({self._total_tokens / self._config.limit * 100:.1f}%)"
            )
            self._maybe_save()

    # -- 查询 --

    def get_usage(self) -> dict:
        """获取当前使用统计"""
        with self._lock:
            total = self._total_tokens
            limit = self._config.limit
        return {
            "total_tokens": total,
            "limit": limit,
            "percent": round(total / limit * 100, 2) if limit > 0 else 0,
            "enabled": self._config.enabled,
            "exceeded": total >= limit if self._config.enabled else False,
        }

    # -- 重置 --

    def reset(self) -> None:
        """重置全局 token 计数器为 0，并立即持久化到文件"""
        with self._lock:
            old = self._total_tokens
            self._total_tokens = 0
            self._last_saved_tokens = 0
            self._save_to_file()
        logger.info(f"[TokenBudget] 计数器已重置 (原累计: {old:,} tokens)")

    # -- 持久化 --

    def force_save(self) -> None:
        """强制立即保存 token 用量到文件（程序退出前调用）"""
        with self._lock:
            self._save_to_file()

    def _resolve_persist_path(self) -> str:
        """解析持久化文件的绝对路径"""
        return get_abs_path(self._config.persist_path)

    def _maybe_save(self) -> None:
        """检查是否需要持久化（当前累计与上次保存的差值 >= save_interval）"""
        delta = self._total_tokens - self._last_saved_tokens
        if delta >= self._config.save_interval:
            self._save_to_file()

    def _save_to_file(self) -> None:
        """将当前 token 计数写入 JSON 文件"""
        filepath = self._resolve_persist_path()
        data = {
            "total_tokens": self._total_tokens,
            "limit": self._config.limit,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._last_saved_tokens = self._total_tokens
            logger.debug(
                f"[TokenBudget] 已持久化到文件: {filepath} "
                f"(total_tokens={self._total_tokens:,})"
            )
        except OSError as e:
            logger.warning(f"[TokenBudget] 持久化写入失败: {e}")

    def _load_from_file(self) -> int:
        """从 JSON 文件恢复上次的 token 计数

        Returns:
            上次保存的 total_tokens，若文件不存在或解析失败则返回 0
        """
        filepath = self._resolve_persist_path()
        if not os.path.isfile(filepath):
            logger.debug(f"[TokenBudget] 持久化文件不存在，从 0 开始计数: {filepath}")
            return 0
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            total = int(data.get("total_tokens", 0))
            last_updated = data.get("last_updated", "未知")
            logger.info(
                f"[TokenBudget] 从文件恢复: {filepath} "
                f"(total_tokens={total:,}, last_updated={last_updated})"
            )
            return total
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning(f"[TokenBudget] 持久化文件读取失败，从 0 开始计数: {e}")
            return 0

    # -- 回调 --

    def get_callback(self) -> TokenBudgetCallbackHandler:
        """获取（或创建）回调处理器单例"""
        if self._callback is None:
            self._callback = TokenBudgetCallbackHandler(self)
        return self._callback


# ---------------------------------------------------------------------------
# 模块级便捷函数（供 API 层调用）
# ---------------------------------------------------------------------------


def get_tracker() -> TokenBudgetTracker:
    """获取全局 TokenBudgetTracker 单例"""
    return TokenBudgetTracker()


def get_token_budget_callback() -> TokenBudgetCallbackHandler:
    """获取全局 TokenBudgetCallbackHandler 单例（供 factory.py 使用）"""
    return get_tracker().get_callback()


def check_budget_or_raise() -> None:
    """检查全局 token 预算，超限则抛出 TokenBudgetExceededError

    在 API 入口处调用此函数即可实现预算门控。
    """
    get_tracker().check_budget_or_raise()


def force_save() -> None:
    """强制立即保存 token 用量到文件

    建议在程序关闭前调用，防止未达 save_interval 阈值的增量丢失。
    """
    get_tracker().force_save()
