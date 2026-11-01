"""行情源注册表。新增源只需实现 adapter 并加到这里。"""
from __future__ import annotations

from src.integrations.sources.base import SourceAdapter, SourceError
from src.integrations.sources.eastmoney import EastmoneyAdapter
from src.integrations.sources.sina import SinaAdapter
from src.integrations.sources.tencent import TencentAdapter

SOURCE_REGISTRY: dict[str, type[SourceAdapter]] = {
    "eastmoney": EastmoneyAdapter,
    "tencent": TencentAdapter,
    "sina": SinaAdapter,
}


def get_adapter(name: str) -> SourceAdapter:
    cls = SOURCE_REGISTRY.get(name)
    if cls is None:
        raise SourceError(f"未知数据源：{name}")
    return cls()
