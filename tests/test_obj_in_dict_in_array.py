"""test_obj_in_dict_in_array.py — 数组中dict里对象测试 (mirrors obj_in_dict_in_array.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class NumberObject:
    def __init__(self, data: int):
        self.value = data

    async def increase(self):
        self.value += 1

    async def get_value(self):
        return self.value


class DictInArrayService:
    async def process(self, items):
        for item in items:
            await item['obj'].increase()
        return (await items[0]['obj'].get_value()) + (await items[1]['obj'].get_value())

    async def process_same(self, items):
        await items[0]['obj'].increase()
        await items[1]['obj'].increase()
        return await items[0]['obj'].get_value()


@pytest.mark.asyncio
async def test_obj_in_dict_in_array():
    await mainFunc(
        DictInArrayService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    a = NumberObject(1)
    b = NumberObject(2)
    v = await main.process([{'obj': a}, {'obj': b}])
    assert_true(v == 5, 'obj in dict in array failed')  # (1+1) + (2+1) = 5


@pytest.mark.asyncio
async def test_same_obj_in_dict_in_array():
    await mainFunc(
        DictInArrayService(),
        lambda _client, main, sid: _check_same(main),
    )


async def _check_same(main):
    a = NumberObject(0)
    v = await main.process_same([{'obj': a}, {'obj': a}])
    assert_true(v == 2, 'same obj in dict in array failed')
