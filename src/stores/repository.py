from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.stores.models import ShopifyStore

logger = logging.getLogger(__name__)

_cache: dict[str, tuple] = {}
_CACHE_TTL = 60


async def get_by_domain(session: AsyncSession, domain: str) -> ShopifyStore | None:
    """Busca loja por domínio. Cache 60s para evitar queries por webhook."""
    now = datetime.now(timezone.utc).timestamp()
    if domain in _cache:
        store, expires = _cache[domain]
        if now < expires:
            return store
        del _cache[domain]

    result = await session.execute(
        select(ShopifyStore).where(
            ShopifyStore.shop_domain == domain,
            ShopifyStore.active.is_(True),
        )
    )
    store = result.scalar_one_or_none()
    if store:
        _cache[domain] = (store, now + _CACHE_TTL)
    return store


def invalidate_cache(domain: str) -> None:
    _cache.pop(domain, None)


async def create_store(session: AsyncSession, data: dict) -> ShopifyStore:
    store = ShopifyStore(id=uuid4(), **data)
    session.add(store)
    await session.flush()
    return store


async def list_stores(session: AsyncSession) -> list[ShopifyStore]:
    result = await session.execute(
        select(ShopifyStore).order_by(ShopifyStore.created_at.desc())
    )
    return list(result.scalars().all())


async def update_store(
    session: AsyncSession, store_id: UUID, data: dict
) -> ShopifyStore | None:
    await session.execute(
        update(ShopifyStore)
        .where(ShopifyStore.id == store_id)
        .values(**data, updated_at=datetime.now(timezone.utc))
    )
    result = await session.execute(
        select(ShopifyStore).where(ShopifyStore.id == store_id)
    )
    store = result.scalar_one_or_none()
    if store:
        invalidate_cache(store.shop_domain)
    return store


async def deactivate_store(session: AsyncSession, store_id: UUID) -> bool:
    result = await session.execute(
        update(ShopifyStore)
        .where(ShopifyStore.id == store_id)
        .values(active=False, updated_at=datetime.now(timezone.utc))
        .returning(ShopifyStore.shop_domain)
    )
    row = result.fetchone()
    if row:
        invalidate_cache(row[0])
        return True
    return False
