"""test_long_time_connection.py — 长连接测试 (mirrors long_time_connection.test.ts)"""
import asyncio
import pytest
from .base_test import mainFunc, assert_true


class SlowService:
    async def slowAdd(self, a, b):
        await asyncio.sleep(0.3)
        return a + b

    async def slowDouble(self, n):
        await asyncio.sleep(0.2)
        return n * 2


@pytest.mark.asyncio
async def test_slow_server_method():
    await mainFunc(
        SlowService(),
        lambda _client, main, sid: _check_slow(main),
    )


async def _check_slow(main):
    v = await main.slowAdd(1, 2)
    assert_true(v == 3, 'long time connection result should be 3')


@pytest.mark.asyncio
async def test_multiple_sequential_slow_requests():
    await mainFunc(
        SlowService(),
        lambda _client, main, sid: _check_sequential(main),
    )


async def _check_sequential(main):
    v1 = await main.slowDouble(3)
    v2 = await main.slowDouble(v1)
    assert_true(v2 == 12, 'sequential slow requests failed')


@pytest.mark.asyncio
async def test_concurrent_slow_requests():
    await mainFunc(
        SlowService(),
        lambda _client, main, sid: _check_concurrent(main),
    )


async def _check_concurrent(main):
    v1, v2, v3 = await asyncio.gather(
        main.slowAdd(1, 2),
        main.slowAdd(3, 4),
        main.slowAdd(5, 6),
    )
    assert_true(v1 == 3, 'concurrent request 1 failed')
    assert_true(v2 == 7, 'concurrent request 2 failed')
    assert_true(v3 == 11, 'concurrent request 3 failed')
