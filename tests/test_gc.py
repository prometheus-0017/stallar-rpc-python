"""test_gc.py — GC 生命周期测试 (mirrors gc.test.ts)"""
import asyncio
import pytest
from xuri_rpc.rpc import asProxy, getProxyHoldingInfo, removeOutdatedProxyObject, autoReRegister
from .base_test import mainFunc, assert_true

GC_SERVER_ID = 'gcServer'


class GCService:
    def getObject(self):
        return asProxy(
            {'add': lambda a, b: a + b}, GC_SERVER_ID
        )


@pytest.mark.asyncio
async def test_proxy_lifecycle_and_gc():
    await mainFunc(
        GCService(),
        lambda _client, main, sid: _check(main, sid),
        {'serverId': GC_SERVER_ID},
    )


async def _check(main, server_id):
    def server_info():
        infos = getProxyHoldingInfo()
        for x in infos:
            if x['hostId'] == server_id:
                return x
        return {'count': 0, 'earliestDate': 0}

    import time

    count = server_info()['count']
    removeOutdatedProxyObject(2.0)
    assert_true(
        server_info()['count'] == count,
        'count should not change without new proxies',
    )

    v = await main.getObject()
    assert_true(
        count + 1 == server_info()['count'],
        'count should increase by 1',
    )

    await asyncio.sleep(1.0)
    now = time.time()
    earliest = server_info()['earliestDate']
    assert_true(
        now - earliest >= 0.7,
        'earliestDate should be at least 700ms ago',
    )

    await autoReRegister()
    now2 = time.time()
    earliest2 = server_info()['earliestDate']
    assert_true(
        now2 - earliest2 <= 0.2,
        'earliestDate should be refreshed after reRegister',
    )

    await asyncio.sleep(0.5)
    count = server_info()['count']
    removeOutdatedProxyObject(0.05)
    assert_true(
        server_info()['count'] < count,
        'outdated proxies should be removed',
    )
