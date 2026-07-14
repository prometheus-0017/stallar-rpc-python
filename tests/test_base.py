"""test_base.py — 基础加法测试 (mirrors base.test.ts)"""
import pytest
from .base_test import mainFunc


class AddService:
    def add(self, a, b):
        return a + b


@pytest.mark.asyncio
async def test_add_two_numbers():
    await mainFunc(
        AddService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    v = await main.add(1, 2)
    assert v == 3
