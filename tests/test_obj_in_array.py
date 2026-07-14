"""test_obj_in_array.py — 数组中对象测试 (mirrors obj_in_array.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class NumberObject:
    def __init__(self, data: int):
        self.value = data

    async def increase(self):
        self.value += 1

    async def get_value(self):
        return self.value


class ObjInArrayService:
    async def add(self, pack):
        a, b, c = pack[0], pack[1], pack[2]
        await a.increase()
        await c.increase()
        await b.increase()
        return (await a.get_value()) + (await b.get_value())


@pytest.mark.asyncio
async def test_obj_in_array():
    await mainFunc(
        ObjInArrayService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    a = NumberObject(0)
    v = await main.add([a, NumberObject(0), a])
    assert_true(v == 3, 'obj in array false')
