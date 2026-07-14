"""test_null.py — None 参数测试 (mirrors null.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class NullService:
    def add(self, a, b, callback):
        assert_true(callback is None, 'callback should be None')
        return a + b


@pytest.mark.asyncio
async def test_null_argument():
    await mainFunc(
        NullService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    v = await main.add(1, 2, None)
    assert_true(v == 3, 'result should be 3')
