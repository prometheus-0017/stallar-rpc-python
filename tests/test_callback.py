"""test_callback.py — 回调测试 (mirrors callback.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class CallbackService:
    def add(self, a, b, callback):
        callback(a + b)
        return a + b


@pytest.mark.asyncio
async def test_callback_argument():
    await mainFunc(
        CallbackService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    callback_val = None

    def on_callback(val):
        nonlocal callback_val
        callback_val = val

    v = await main.add(1, 2, on_callback)
    assert v == 3
    # Give the callback task time to execute
    import asyncio
    await asyncio.sleep(0.05)
    assert_true(callback_val == 3, 'callback value should be 3')
