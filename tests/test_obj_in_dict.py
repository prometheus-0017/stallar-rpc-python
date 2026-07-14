"""test_obj_in_dict.py — dict 中对象测试 (mirrors obj_in_dict.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class NumberObject:
    def __init__(self, data: int):
        self.value = data

    async def increase(self):
        self.value += 1

    async def get_value(self):
        return self.value


class ObjInDictService:
    async def add(self, pack):
        await pack['a'].increase()
        await pack['c'].increase()
        await pack['b'].increase()
        return (await pack['a'].get_value()) + (await pack['b'].get_value())


@pytest.mark.asyncio
async def test_obj_in_dict():
    await mainFunc(
        ObjInDictService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    a = NumberObject(0)
    pack = {'a': a, 'b': NumberObject(0), 'c': a}
    v = await main.add(pack)
    assert_true(v == 3, 'obj in dict false')
