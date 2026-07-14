"""test_return_types.py — 返回类型测试 (mirrors return_types.test.ts)"""
import pytest
from .base_test import mainFunc, assert_true


class GreetService:
    def greet(self, name):
        return f'hello {name}'


class BoolService:
    def isPositive(self, n):
        return n > 0


class Data_Service:
    def getData(self):
        return {'a': 1, 'b': 'hello', 'c': True}


class VoidService:
    def doNothing(self):
        return None


class NumberService:
    def double(self, n):
        return n * 2


class ZeroService:
    def zero(self):
        return 0


class EmptyStrService:
    def emptyStr(self):
        return ''


class NestedService:
    def getNested(self):
        return {'outer': {'inner': 42}}


class ListService:
    def getList(self):
        return [1, 'two', True]


@pytest.mark.asyncio
async def test_return_string():
    await mainFunc(GreetService(), lambda _c, m, s: _check_string(m))


async def _check_string(main):
    v = await main.greet('world')
    assert_true(v == 'hello world', 'string return failed')


@pytest.mark.asyncio
async def test_return_boolean():
    await mainFunc(BoolService(), lambda _c, m, s: _check_bool(m))


async def _check_bool(main):
    v1 = await main.isPositive(5)
    v2 = await main.isPositive(-1)
    assert_true(v1 is True, 'boolean true return failed')
    assert_true(v2 is False, 'boolean false return failed')


@pytest.mark.asyncio
async def test_return_plain_dict():
    await mainFunc(Data_Service(), lambda _c, m, s: _check_dict(m))


async def _check_dict(main):
    v = await main.getData()
    assert_true(v['a'] == 1, 'dict.a return failed')
    assert_true(v['b'] == 'hello', 'dict.b return failed')
    assert_true(v['c'] is True, 'dict.c return failed')


@pytest.mark.asyncio
async def test_return_none_for_void():
    await mainFunc(VoidService(), lambda _c, m, s: _check_none(m))


async def _check_none(main):
    v = await main.doNothing()
    assert_true(v is None, 'void return should be None')


@pytest.mark.asyncio
async def test_return_number():
    await mainFunc(NumberService(), lambda _c, m, s: _check_number(m))


async def _check_number(main):
    v = await main.double(7)
    assert_true(v == 14, 'number return failed')


@pytest.mark.asyncio
async def test_return_zero():
    await mainFunc(ZeroService(), lambda _c, m, s: _check_zero(m))


async def _check_zero(main):
    v = await main.zero()
    assert_true(v == 0, 'zero return failed')


@pytest.mark.asyncio
async def test_return_empty_string():
    await mainFunc(EmptyStrService(), lambda _c, m, s: _check_empty(m))


async def _check_empty(main):
    v = await main.emptyStr()
    assert_true(v == '', 'empty string return failed')


@pytest.mark.asyncio
async def test_return_nested_dict():
    await mainFunc(NestedService(), lambda _c, m, s: _check_nested(m))


async def _check_nested(main):
    v = await main.getNested()
    assert_true(v['outer']['inner'] == 42, 'nested dict return failed')


@pytest.mark.asyncio
async def test_return_list_of_primitives():
    await mainFunc(ListService(), lambda _c, m, s: _check_list(m))


async def _check_list(main):
    v = await main.getList()
    assert_true(v[0] == 1, 'list[0] return failed')
    assert_true(v[1] == 'two', 'list[1] return failed')
    assert_true(v[2] is True, 'list[2] return failed')
