"""test_null_in_dict.py — dict 中 None 测试 (mirrors null_in_dict_test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class NullInDictService:
    def checkNull(self, pack):
        assert_true(pack['b'] is None, 'b should be None')
        assert_true(pack['c'] is None, 'c should be None')
        return pack['a'] + 1


class MixedNullService:
    def mixedNull(self, pack):
        assert_true(pack['x'] == 10, 'x should be 10')
        assert_true(pack['y'] is None, 'y should be None')
        assert_true(pack['z'] == 30, 'z should be 30')
        return pack['x'] + pack['z']


@pytest.mark.asyncio
async def test_null_in_dict():
    await mainFunc(
        NullInDictService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    v = await main.checkNull({'a': 1, 'b': None, 'c': None})
    assert_true(v == 2, 'result should be 2')


@pytest.mark.asyncio
async def test_mixed_null_in_dict():
    await mainFunc(
        MixedNullService(),
        lambda _client, main, sid: _check_mixed(main),
    )


async def _check_mixed(main):
    v = await main.mixedNull({'x': 10, 'y': None, 'z': 30})
    assert_true(v == 40, 'result should be 40')
