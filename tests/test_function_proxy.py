"""test_function_proxy.py — 函数代理测试 (mirrors function_proxy.test.ts)"""
import pytest
from xuri_rpc.rpc import asProxy
from .base_test import mainFunc, assert_true

FP_SERVER_ID = 'funcProxyServer'
FP_CLIENT_ID = 'funcProxyClient'


class MultiplierService:
    def getMultiplier(self):
        return asProxy(
            lambda a, b: a * b, FP_SERVER_ID
        )


class CounterService:
    def __init__(self):
        self.call_count = 0
        self.server_id = FP_SERVER_ID + '2'

    def getCounter(self):
        self.call_count += 1
        return asProxy(self._counter, self.server_id)

    def _counter(self):
        return self.call_count


class CallbackInvokeService:
    def invokeCallback(self, cb, value):
        return cb(value)


@pytest.mark.asyncio
async def test_callable_function_proxy():
    await mainFunc(
        MultiplierService(),
        lambda _client, main, sid: _check_multiplier(main),
        {'serverId': FP_SERVER_ID, 'clientId': FP_CLIENT_ID},
    )


async def _check_multiplier(main):
    multiplier = await main.getMultiplier()
    result = await multiplier(3, 4)
    assert_true(result == 12, 'function proxy __call__ failed')


@pytest.mark.asyncio
async def test_counter_function_proxy():
    await mainFunc(
        CounterService(),
        lambda _client, main, sid: _check_counter(main),
        {'serverId': FP_SERVER_ID + '2', 'clientId': FP_CLIENT_ID + '2'},
    )


async def _check_counter(main):
    counter = await main.getCounter()
    v1 = await counter()
    v2 = await counter()
    v3 = await counter()
    assert_true(v1 == 1, 'counter first call failed')
    assert_true(v2 == 2, 'counter second call failed')
    assert_true(v3 == 3, 'counter third call failed')


@pytest.mark.asyncio
async def test_callback_via_asProxy():
    await mainFunc(
        CallbackInvokeService(),
        lambda _client, main, sid: _check_callback(main),
        {'serverId': FP_SERVER_ID + '3', 'clientId': FP_CLIENT_ID + '3'},
    )


async def _check_callback(main):
    result = await main.invokeCallback(
        asProxy(lambda n: n * 10, FP_CLIENT_ID + '3'), 5
    )
    assert_true(result == 50, 'callback via asProxy failed')
