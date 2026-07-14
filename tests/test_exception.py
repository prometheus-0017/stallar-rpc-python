"""test_exception.py — 异常传播测试 (mirrors exception.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class ExceptionService:
    def add(self, a, b):
        raise Exception('testException')


@pytest.mark.asyncio
async def test_exception_propagated():
    await mainFunc(
        ExceptionService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    flag = False
    try:
        await main.add(1, 2)
    except Exception:
        flag = True
    assert_true(flag, 'exception should have been caught')
