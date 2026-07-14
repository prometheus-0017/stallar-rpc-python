"""
rpc_test.py — All Python tests consolidated.
Run with: pytest rpc_test.py -v
"""
import asyncio
import struct
import sys
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from xuri_rpc import (
    Client, MessageReceiver, PreArgObj, setHostId,
    PlainProxyManager, RunnableProxyManager,
    _deleteProxy, _deleteProxyById,
    asProxy, generateErrorReply, getMessageReceiver,
    getProxyHoldingInfo, removeOutdatedProxyObject, autoReRegister,
    RpcMessage, ISender,
)
from xuri_rpc.local_serialization_sender import DumpChannel, createServer as localCreateServer, createMain as localCreateMain


# ===========================================================================
# Helper: in-process RPC setup (mirrors base_test.py / base.ts)
# ===========================================================================

_id_counter: int = 0


async def mainFunc(
    mainObject: Any,
    testProcess: Callable[[Client, Any, str], Any],
    customHostIds: Optional[Dict[str, str]] = None,
) -> None:
    global _id_counter
    idx = _id_counter
    _id_counter += 1
    server_id = (customHostIds or {}).get('serverId') or f'server{idx}'
    client_id = (customHostIds or {}).get('clientId') or f'client{idx}'
    channel = DumpChannel()
    serve = await localCreateServer(server_id, channel)
    _recv, _serve = serve(mainObject)
    client, main = await localCreateMain(client_id, channel)
    await testProcess(client, main, server_id)


def assert_true(condition: bool, text: Optional[str] = None) -> None:
    if not condition:
        raise AssertionError(text or 'assertion failed')


class DirectSender(ISender):
    """Test sender that dispatches directly to a MessageReceiver."""
    def __init__(self, client_callback: Client, msg_receiver: MessageReceiver) -> None:
        self.client_callback: Client = client_callback
        self.msg_receiver: MessageReceiver = msg_receiver

    async def send(self, message: RpcMessage) -> None:
        await self.msg_receiver.onReceiveMessage(message, self.client_callback)


# ===========================================================================
# Service classes
# ===========================================================================

class AddService:
    def add(self, a: Any, b: Any) -> Any:
        return a + b


class ByteService:
    def add(self, a: bytes, b: bytes) -> bytes:
        return a + b


class CallbackService:
    def add(self, a: int, b: int, callback: Callable[[int], None]) -> int:
        callback(a + b)
        return a + b


class NullService:
    def add(self, a: int, b: int, callback: Any) -> int:
        assert_true(callback is None, 'callback should be None')
        return a + b


class NullInDictService:
    def checkNull(self, pack: Dict[str, Any]) -> int:
        assert_true(pack['b'] is None, 'b should be None')
        assert_true(pack['c'] is None, 'c should be None')
        return pack['a'] + 1


class MixedNullService:
    def mixedNull(self, pack: Dict[str, Any]) -> int:
        assert_true(pack['x'] == 10, 'x should be 10')
        assert_true(pack['y'] is None, 'y should be None')
        assert_true(pack['z'] == 30, 'z should be 30')
        return pack['x'] + pack['z']


class GreetService:
    def greet(self, name: str) -> str:
        return f'hello {name}'


class BoolService:
    def isPositive(self, n: int) -> bool:
        return n > 0


class DataService:
    def getData(self) -> Dict[str, Any]:
        return {'a': 1, 'b': 'hello', 'c': True}


class VoidService:
    def doNothing(self) -> None:
        return None


class NumberService:
    def double(self, n: int) -> int:
        return n * 2


class ZeroService:
    def zero(self) -> int:
        return 0


class EmptyStrService:
    def emptyStr(self) -> str:
        return ''


class NestedService:
    def getNested(self) -> Dict[str, Any]:
        return {'outer': {'inner': 42}}


class ListService:
    def getList(self) -> List[Any]:
        return [1, 'two', True]


class SlowService:
    async def slowAdd(self, a: int, b: int) -> int:
        await asyncio.sleep(0.3)
        return a + b

    async def slowDouble(self, n: int) -> int:
        await asyncio.sleep(0.2)
        return n * 2


class EchoService:
    def echo(self, x: Any) -> Any:
        return x


class IdentityService:
    def identity(self, x: Any) -> Any:
        return x


class ExceptionService:
    def add(self, a: Any, b: Any) -> None:
        raise Exception('testException')


class NotFoundService:
    def hello(self) -> str:
        return 'world'


class ExceptionThrowService:
    def throwErr(self) -> None:
        raise Exception('server error')


class _HelloService:
    def hello(self, a: int, b: int, on_result: Callable[[int], Any]) -> int:
        return (on_result(a + b), a + b)[1]


class MainFlowService:
    def __init__(self, hostId: str) -> None:
        self._hostId: str = hostId
        self._say_service: SayService = SayService()

    def hello(self, a: int, b: int, on_result: Callable[[int], Any]) -> int:
        return (on_result(a + b), a + b)[1]

    def getObject(self) -> PreArgObj:
        return asProxy(self._say_service, self._hostId)


class SayService:
    def say(self, name: str) -> None:
        print('hello ', name)


class MainService:
    def hello(self, a: int, b: int, on_result: Callable[[int], Any]) -> int:
        return (on_result(a + b), a + b)[1]

    def getObject(self) -> PreArgObj:
        return asProxy(SayService(), 'backendJs')


class ContextTestService:
    def hello(self, context: Dict[str, Any]) -> str:
        return 'hello'


class ContextTestService2:
    def hello(self, context: Dict[str, Any]) -> str:
        return f"hello {context.get('a')} and {context.get('b')}"


# -- Function proxy services --

FP_SERVER_ID: str = 'funcProxyServer'
FP_CLIENT_ID: str = 'funcProxyClient'


class MultiplierService:
    def getMultiplier(self) -> PreArgObj:
        return asProxy(lambda a, b: a * b, FP_SERVER_ID)


class CounterService:
    def __init__(self) -> None:
        self.call_count: int = 0
        self.server_id: str = FP_SERVER_ID + '2'

    def getCounter(self) -> PreArgObj:
        self.call_count += 1
        return asProxy(self._counter, self.server_id)

    def _counter(self) -> int:
        return self.call_count


class CallbackInvokeService:
    def invokeCallback(self, cb: Callable[[Any], Any], value: Any) -> Any:
        return cb(value)


# -- GC services --

GC_SERVER_ID: str = 'gcServer'


class GCService:
    def getObject(self) -> PreArgObj:
        return asProxy({'add': lambda a, b: a + b}, GC_SERVER_ID)


# -- Obj-in-struct services --

class NumberObject:
    def __init__(self, data: int) -> None:
        self.value: int = data

    async def increase(self) -> None:
        self.value += 1

    async def getValue(self) -> int:
        return self.value


class ObjInArrayService:
    async def add(self, pack: List[Any]) -> int:
        a, b, c = pack[0], pack[1], pack[2]
        await a.increase()
        await c.increase()
        await b.increase()
        return (await a.getValue()) + (await b.getValue())


class ObjInDictService:
    async def add(self, pack: Dict[str, Any]) -> int:
        await pack['a'].increase()
        await pack['c'].increase()
        await pack['b'].increase()
        return (await pack['a'].getValue()) + (await pack['b'].getValue())


class DictInArrayService:
    async def process(self, items: List[Dict[str, Any]]) -> int:
        for item in items:
            await item['obj'].increase()
        return (await items[0]['obj'].getValue()) + (await items[1]['obj'].getValue())

    async def process_same(self, items: List[Dict[str, Any]]) -> int:
        await items[0]['obj'].increase()
        await items[1]['obj'].increase()
        return await items[0]['obj'].getValue()


# ===========================================================================
# Byte helpers
# ===========================================================================

def int2bytes(value: int) -> bytes:
    return struct.pack('>i', value)

def byte2int(data: bytes, offset: int = 0) -> int:
    return struct.unpack('>i', data[offset:offset + 4])[0]


# ===========================================================================
# Tests: Basic
# ===========================================================================

@pytest.mark.asyncio
async def test_add_two_numbers():
    await mainFunc(AddService(), lambda _c, m, s: _check_add(m))

async def _check_add(main):
    v = await main.add(1, 2)
    assert v == 3


# ===========================================================================
# Tests: Byte transfer
# ===========================================================================

@pytest.mark.asyncio
async def test_byte_transmit_and_concat():
    await mainFunc(ByteService(), lambda _c, m, s: _check_byte(m))

async def _check_byte(main):
    v = await main.add(int2bytes(1), int2bytes(2))
    a = byte2int(v)
    b = byte2int(v, 4)
    assert_true(a + b == 3, 'byte concat failed')


# ===========================================================================
# Tests: Callback
# ===========================================================================

@pytest.mark.asyncio
async def test_callback_argument():
    await mainFunc(CallbackService(), lambda _c, m, s: _check_callback(m))

async def _check_callback(main):
    callback_val = None
    def on_cb(val):
        nonlocal callback_val
        callback_val = val
    v = await main.add(1, 2, on_cb)
    assert v == 3
    await asyncio.sleep(0.05)
    assert_true(callback_val == 3, 'callback value should be 3')


# ===========================================================================
# Tests: Null handling
# ===========================================================================

@pytest.mark.asyncio
async def test_null_argument():
    await mainFunc(NullService(), lambda _c, m, s: _check_null(m))

async def _check_null(main):
    v = await main.add(1, 2, None)
    assert_true(v == 3, 'result should be 3')


@pytest.mark.asyncio
async def test_null_in_dict():
    await mainFunc(NullInDictService(), lambda _c, m, s: _check_null_dict(m))

async def _check_null_dict(main):
    v = await main.checkNull({'a': 1, 'b': None, 'c': None})
    assert_true(v == 2, 'result should be 2')


@pytest.mark.asyncio
async def test_mixed_null_in_dict():
    await mainFunc(MixedNullService(), lambda _c, m, s: _check_mixed_null(m))

async def _check_mixed_null(main):
    v = await main.mixedNull({'x': 10, 'y': None, 'z': 30})
    assert_true(v == 40, 'result should be 40')


# ===========================================================================
# Tests: Return types
# ===========================================================================

@pytest.mark.asyncio
async def test_return_string():
    await mainFunc(GreetService(), lambda _c, m, s: _chk_str(m))

async def _chk_str(main):
    v = await main.greet('world')
    assert_true(v == 'hello world', 'string return failed')


@pytest.mark.asyncio
async def test_return_boolean():
    await mainFunc(BoolService(), lambda _c, m, s: _chk_bool(m))

async def _chk_bool(main):
    assert_true((await main.isPositive(5)) is True)
    assert_true((await main.isPositive(-1)) is False)


@pytest.mark.asyncio
async def test_return_plain_dict():
    await mainFunc(DataService(), lambda _c, m, s: _chk_dict(m))

async def _chk_dict(main):
    v = await main.getData()
    assert_true(v['a'] == 1)
    assert_true(v['b'] == 'hello')
    assert_true(v['c'] is True)


@pytest.mark.asyncio
async def test_return_none_for_void():
    await mainFunc(VoidService(), lambda _c, m, s: _chk_void(m))

async def _chk_void(main):
    assert_true((await main.doNothing()) is None)


@pytest.mark.asyncio
async def test_return_number():
    await mainFunc(NumberService(), lambda _c, m, s: _chk_num(m))

async def _chk_num(main):
    assert_true((await main.double(7)) == 14)


@pytest.mark.asyncio
async def test_return_zero():
    await mainFunc(ZeroService(), lambda _c, m, s: _chk_zero(m))

async def _chk_zero(main):
    assert_true((await main.zero()) == 0)


@pytest.mark.asyncio
async def test_return_empty_string():
    await mainFunc(EmptyStrService(), lambda _c, m, s: _chk_empty(m))

async def _chk_empty(main):
    assert_true((await main.emptyStr()) == '')


@pytest.mark.asyncio
async def test_return_nested_dict():
    await mainFunc(NestedService(), lambda _c, m, s: _chk_nested(m))

async def _chk_nested(main):
    v = await main.getNested()
    assert_true(v['outer']['inner'] == 42)


@pytest.mark.asyncio
async def test_return_list():
    await mainFunc(ListService(), lambda _c, m, s: _chk_list(m))

async def _chk_list(main):
    v = await main.getList()
    assert_true(v[0] == 1)
    assert_true(v[1] == 'two')
    assert_true(v[2] is True)


# ===========================================================================
# Tests: Exception propagation
# ===========================================================================

@pytest.mark.asyncio
async def test_exception_propagated():
    await mainFunc(ExceptionService(), lambda _c, m, s: _check_exc(m))

async def _check_exc(main):
    flag = False
    try:
        await main.add(1, 2)
    except Exception:
        flag = True
    assert_true(flag, 'exception should have been caught')


# ===========================================================================
# Tests: Long time connection
# ===========================================================================

@pytest.mark.asyncio
async def test_slow_server_method():
    await mainFunc(SlowService(), lambda _c, m, s: _check_slow(m))

async def _check_slow(main):
    v = await main.slowAdd(1, 2)
    assert_true(v == 3)


@pytest.mark.asyncio
async def test_multiple_sequential_slow_requests():
    await mainFunc(SlowService(), lambda _c, m, s: _check_seq(m))

async def _check_seq(main):
    v1 = await main.slowDouble(3)
    v2 = await main.slowDouble(v1)
    assert_true(v2 == 12)


@pytest.mark.asyncio
async def test_concurrent_slow_requests():
    await mainFunc(SlowService(), lambda _c, m, s: _check_conc(m))

async def _check_conc(main):
    v1, v2, v3 = await asyncio.gather(
        main.slowAdd(1, 2), main.slowAdd(3, 4), main.slowAdd(5, 6),
    )
    assert_true(v1 == 3)
    assert_true(v2 == 7)
    assert_true(v3 == 11)


# ===========================================================================
# Tests: Obj in array / dict
# ===========================================================================

@pytest.mark.asyncio
async def test_obj_in_array():
    await mainFunc(ObjInArrayService(), lambda _c, m, s: _chk_oia(m))

async def _chk_oia(main):
    a = NumberObject(0)
    v = await main.add([a, NumberObject(0), a])
    assert_true(v == 3, 'obj in array false')


@pytest.mark.asyncio
async def test_obj_in_dict():
    await mainFunc(ObjInDictService(), lambda _c, m, s: _chk_oid(m))

async def _chk_oid(main):
    a = NumberObject(0)
    pack = {'a': a, 'b': NumberObject(0), 'c': a}
    v = await main.add(pack)
    assert_true(v == 3, 'obj in dict false')


@pytest.mark.asyncio
async def test_obj_in_dict_in_array():
    await mainFunc(DictInArrayService(), lambda _c, m, s: _chk_dia(m))

async def _chk_dia(main):
    a = NumberObject(1)
    b = NumberObject(2)
    v = await main.process([{'obj': a}, {'obj': b}])
    assert_true(v == 5, 'obj in dict in array failed')


@pytest.mark.asyncio
async def test_same_obj_in_dict_in_array():
    await mainFunc(DictInArrayService(), lambda _c, m, s: _chk_dia_same(m))

async def _chk_dia_same(main):
    a = NumberObject(0)
    v = await main.process_same([{'obj': a}, {'obj': a}])
    assert_true(v == 2, 'same obj in dict in array failed')


# ===========================================================================
# Tests: Function proxy
# ===========================================================================

@pytest.mark.asyncio
async def test_callable_function_proxy():
    await mainFunc(
        MultiplierService(),
        lambda _c, m, s: _chk_multiplier(m),
        {'serverId': FP_SERVER_ID, 'clientId': FP_CLIENT_ID},
    )

async def _chk_multiplier(main):
    multiplier = await main.getMultiplier()
    result = await multiplier(3, 4)
    assert_true(result == 12, 'function proxy __call__ failed')


@pytest.mark.asyncio
async def test_counter_function_proxy():
    await mainFunc(
        CounterService(),
        lambda _c, m, s: _chk_counter(m),
        {'serverId': FP_SERVER_ID + '2', 'clientId': FP_CLIENT_ID + '2'},
    )

async def _chk_counter(main):
    counter = await main.getCounter()
    v1 = await counter()
    v2 = await counter()
    v3 = await counter()
    assert_true(v1 == 1)
    assert_true(v2 == 2)
    assert_true(v3 == 3)


@pytest.mark.asyncio
async def test_callback_via_asProxy():
    await mainFunc(
        CallbackInvokeService(),
        lambda _c, m, s: _chk_asproxy_cb(m),
        {'serverId': FP_SERVER_ID + '3', 'clientId': FP_CLIENT_ID + '3'},
    )

async def _chk_asproxy_cb(main):
    result = await main.invokeCallback(
        asProxy(lambda n: n * 10, FP_CLIENT_ID + '3'), 5
    )
    assert_true(result == 50, 'callback via asProxy failed')


# ===========================================================================
# Tests: GC lifecycle
# ===========================================================================

@pytest.mark.asyncio
async def test_proxy_lifecycle_and_gc():
    await mainFunc(
        GCService(),
        lambda _c, m, s: _chk_gc(m, s),
        {'serverId': GC_SERVER_ID},
    )

async def _chk_gc(main, server_id):
    def server_info():
        infos = getProxyHoldingInfo()
        for x in infos:
            if x['hostId'] == server_id:
                return x
        return {'count': 0, 'earliestDate': 0}

    count = server_info()['count']
    removeOutdatedProxyObject(2.0)
    assert_true(server_info()['count'] == count)

    v = await main.getObject()
    assert_true(count + 1 == server_info()['count'])

    await asyncio.sleep(1.0)
    now = time.time()
    earliest = server_info()['earliestDate']
    assert_true(now - earliest >= 0.7)

    await autoReRegister()
    now2 = time.time()
    earliest2 = server_info()['earliestDate']
    assert_true(now2 - earliest2 <= 0.2)

    await asyncio.sleep(0.5)
    count = server_info()['count']
    removeOutdatedProxyObject(0.05)
    assert_true(server_info()['count'] < count)


# ===========================================================================
# Tests: Context (interceptor)
# ===========================================================================

@pytest.mark.asyncio
async def test_context_object():
    setHostId('frontJs')
    hostId = 'backendJs'
    messageReceiver_backend = MessageReceiver(hostId)
    messageReceiver_backend.setMain(MainService())
    messageReceiver_backend.setObject('contextTest', ContextTestService(), True)
    messageReceiver_backend.setResultAutoWrapper(lambda x: x)

    client = Client()
    client_on_backend = Client(hostId)
    sender = DirectSender(client_on_backend, messageReceiver_backend)
    back_sender = DirectSender(client, getMessageReceiver())
    client.setSender(lambda: sender)
    client_on_backend.setSender(lambda: back_sender)
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.getObject('contextTest')
    result = await rpc.hello()
    assert result == 'hello'


@pytest.mark.asyncio
async def test_interceptor_chain():
    setHostId('frontJs')
    hostId = 'backendJs'
    messageReceiver_backend = MessageReceiver(hostId)
    messageReceiver_backend.setMain(MainService())
    messageReceiver_backend.setObject('contextTest', ContextTestService2(), True)
    messageReceiver_backend.setResultAutoWrapper(lambda x: x)

    async def interceptor1(ctx, msg, clt, next_fn):
        ctx['a'] = 'mike'
        await next_fn()
        ctx.pop('a', None)

    async def interceptor2(ctx, msg, clt, next_fn):
        ctx['b'] = 'jack'
        await next_fn()
        ctx.pop('b', None)

    messageReceiver_backend.addInterceptor(interceptor1)
    messageReceiver_backend.addInterceptor(interceptor2)

    client = Client()
    client_on_backend = Client(hostId)
    sender = DirectSender(client_on_backend, messageReceiver_backend)
    back_sender = DirectSender(client, getMessageReceiver())
    client.setSender(lambda: sender)
    client_on_backend.setSender(lambda: back_sender)
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.getObject('contextTest')
    result = await rpc.hello()
    assert result == 'hello mike and jack'


# ===========================================================================
# Tests: Full flow (main)
# ===========================================================================

@pytest.mark.asyncio
async def test_full_flow():
    setHostId('frontJs')
    hostId = 'backendJs'
    messageReceiver_backend = MessageReceiver(hostId)
    messageReceiver_backend.setMain(MainFlowService(hostId))
    messageReceiver_backend.setResultAutoWrapper(lambda x: x)

    client = Client()
    client_on_backend = Client(hostId)
    sender = DirectSender(client_on_backend, messageReceiver_backend)
    back_sender = DirectSender(client, getMessageReceiver())
    client.setSender(lambda: sender)
    client_on_backend.setSender(lambda: back_sender)
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.getMain()

    callback_val = None
    def callback(a):
        nonlocal callback_val
        callback_val = a

    result = await rpc.hello(1, 2, asProxy(callback))
    await asyncio.sleep(0.05)
    assert callback_val == 3
    assert result == 3

    remote_object = await rpc.getObject()
    await remote_object.say('world')


# ===========================================================================
# Tests: Error handling
# ===========================================================================

@pytest.mark.asyncio
async def test_setSender_can_be_called_multiple_times():
    client = Client()
    client.setSender(lambda: DirectSender(client, MessageReceiver()))
    client.setSender(lambda: DirectSender(client, MessageReceiver()))


@pytest.mark.asyncio
async def test_onReceiveMessage_null_client():
    receiver = MessageReceiver('errTestNull')
    with pytest.raises(ValueError, match='clientForCallback must not be None'):
        await receiver.onReceiveMessage(
            {'id': 'test', 'idFor': None, 'meta': {}, 'status': 200}, None
        )


@pytest.mark.asyncio
async def test_onReceiveMessage_non_client():
    receiver = MessageReceiver('errTestNonClient')
    with pytest.raises(TypeError, match='clientForCallback must be a Client'):
        await receiver.onReceiveMessage(
            {'id': 'test', 'idFor': None, 'meta': {}, 'status': 200}, object()
        )


@pytest.mark.asyncio
async def test_object_not_found_error():
    server_hostId = 'errNotFoundServer'
    client_hostId = 'errNotFoundClient'
    setHostId(client_hostId)

    messageReceiver_backend = MessageReceiver(server_hostId)
    messageReceiver_backend.setMain(NotFoundService())
    messageReceiver_backend.setResultAutoWrapper(lambda x: x)

    client = Client(client_hostId)
    client_on_backend = Client(server_hostId)
    sender = DirectSender(client_on_backend, messageReceiver_backend)
    back_sender = DirectSender(client, MessageReceiver(client_hostId))
    client.setSender(lambda: sender)
    client_on_backend.setSender(lambda: back_sender)
    client.setArgsAutoWrapper(lambda x: x)

    error_caught = False
    try:
        await client.waitForRequest({
            'id': 'testReq1', 'objectId': 'nonExistentObj',
            'method': 'someMethod', 'args': [], 'meta': {},
        })
    except Exception as e:
        error_caught = True
        assert e.response['status'] == 100
        assert e.response['trace'] == 'object not found'
    assert error_caught


def test_generateErrorReply():
    request = {'id': 'req123', 'meta': {}, 'method': 'testMethod', 'objectId': 'obj1', 'args': []}
    reply = generateErrorReply(request, 'something went wrong', 500)
    assert reply['idFor'] == 'req123'
    assert reply['status'] == 500
    assert reply['trace'] == 'something went wrong'


def test_generateErrorReply_default_status():
    request = {'id': 'req456', 'meta': {}, 'method': 'testMethod', 'objectId': 'obj1', 'args': []}
    reply = generateErrorReply(request, 'default error')
    assert reply['status'] == 500


@pytest.mark.asyncio
async def test_server_exception_propagated_to_client():
    server_hostId = 'errExceptionServer'
    client_hostId = 'errExceptionClient'
    setHostId(client_hostId)

    messageReceiver_backend = MessageReceiver(server_hostId)
    messageReceiver_backend.setMain(ExceptionThrowService())
    messageReceiver_backend.setResultAutoWrapper(lambda x: x)

    client = Client(client_hostId)
    client_on_backend = Client(server_hostId)
    sender = DirectSender(client_on_backend, messageReceiver_backend)
    back_sender = DirectSender(client, MessageReceiver(client_hostId))
    client.setSender(lambda: sender)
    client_on_backend.setSender(lambda: back_sender)
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.getMain()
    error_caught = False
    try:
        await rpc.throwErr()
    except Exception as e:
        error_caught = True
        assert e.response['status'] == -1
        assert 'server error' in e.response.get('trace', '')
    assert error_caught


# ===========================================================================
# Tests: Unit API — PlainProxyManager
# ===========================================================================

class TestPlainProxyManager:
    def test_set_and_getById(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id1')
        assert manager.getById('id1') is obj
        assert manager.get(obj) == 'id1'
        assert manager.has(obj) is True

    def test_delete_by_reference(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id2')
        assert manager.has(obj) is True
        manager.delete(obj)
        assert manager.has(obj) is False
        assert manager.getById('id2') is None

    def test_deleteById(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id3')
        manager.deleteById('id3')
        assert manager.has(obj) is False
        assert manager.getById('id3') is None

    def test_handle_multiple_objects(self):
        manager = PlainProxyManager()
        obj1 = {'name': 'a'}
        obj2 = {'name': 'b'}
        manager.set(obj1, 'id1')
        manager.set(obj2, 'id2')
        assert manager.get(obj1) == 'id1'
        assert manager.get(obj2) == 'id2'
        assert manager.getById('id1') is obj1
        assert manager.getById('id2') is obj2

    def test_overwrite_with_same_id(self):
        manager = PlainProxyManager()
        obj1 = {'name': 'a'}
        obj2 = {'name': 'b'}
        manager.set(obj1, 'id1')
        manager.set(obj2, 'id1')
        assert manager.getById('id1') is obj2

    def test_reRegister_updates_last_registered(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id1')
        before = manager.reverseProxyMap['id1'].lastRegistered
        time.sleep(0.01)
        manager.reRegister('id1')
        after = manager.reverseProxyMap['id1'].lastRegistered
        assert after >= before


# ===========================================================================
# Tests: Unit API — RunnableProxyManager
# ===========================================================================

class TestRunnableProxyManager:
    def test_set_and_get_proxy(self):
        manager = RunnableProxyManager()
        class _Proxy:
            def method(self): pass
        proxy = _Proxy()
        client = Client()
        manager.set('id1', proxy, client)
        assert manager.get('id1') is proxy

    def test_return_none_for_nonexistent_id(self):
        manager = RunnableProxyManager()
        assert manager.get('nonExistent') is None

    def test_track_client_to_proxy_id_mapping(self):
        manager = RunnableProxyManager()
        class _Proxy:
            def method(self): pass
        proxy = _Proxy()
        client = Client()
        manager.set('id1', proxy, client)
        assert client in manager.clientMap
        assert 'id1' in manager.clientMap[client]

    def test_multiple_proxies_for_same_client(self):
        manager = RunnableProxyManager()
        class _P1:
            def method1(self): pass
        class _P2:
            def method2(self): pass
        p1 = _P1()
        p2 = _P2()
        client = Client()
        manager.set('id1', p1, client)
        manager.set('id2', p2, client)
        assert len(manager.clientMap[client]) == 2


# ===========================================================================
# Tests: Unit API — PreArgObj
# ===========================================================================

class TestPreArgObj:
    def test_create_proxy_type(self):
        obj = PreArgObj('proxy', {'id': 'test', 'hostId': 'h1', 'members': []})
        assert obj.type == 'proxy'
        assert obj.data == {'id': 'test', 'hostId': 'h1', 'members': []}

    def test_create_data_type(self):
        obj = PreArgObj('data', {'value': 42})
        assert obj.type == 'data'
        assert obj.data == {'value': 42}

    def test_create_null_type(self):
        obj = PreArgObj(None, None)
        assert obj.type is None
        assert obj.data is None


# ===========================================================================
# Tests: Unit API — Client
# ===========================================================================

class TestClient:
    def test_getHostId_from_option(self):
        setHostId('unitTestHost')
        client = Client()
        assert client.getHostId() == 'unitTestHost'

    def test_use_own_hostId(self):
        client = Client('customHost')
        assert client.getHostId() == 'customHost'


# ===========================================================================
# Tests: Unit API — MessageReceiver
# ===========================================================================

class TestMessageReceiver:
    def test_currentWaitingCount(self):
        setHostId('waitingCountTest')
        receiver = MessageReceiver('waitingCountTest')
        assert receiver.currentWaitingCount() == 0

    def test_set_and_getMainObject(self):
        setHostId('setMainTest')
        receiver = MessageReceiver('setMainTest')
        class MainObj:
            def hello(self):
                return 'world'
        receiver.setMain(MainObj())
        pm = receiver.getProxyManager()
        main_obj = pm.getById('main')
        assert main_obj is not None
        assert main_obj.hello() == 'world'

    def test_setObject_with_context(self):
        setHostId('setObjWithCtx')
        receiver = MessageReceiver('setObjWithCtx')
        receiver.setObject('myObj', {'doStuff': lambda: 42}, True)
        pm = receiver.getProxyManager()
        assert pm.getById('myObj') is not None
        assert 'myObj' in receiver.objectWithContext

    def test_setObject_without_context(self):
        setHostId('setObjNoCtx')
        receiver = MessageReceiver('setObjNoCtx')
        receiver.setObject('myObj2', {'doStuff': lambda: 42}, False)
        assert 'myObj2' not in receiver.objectWithContext

    def test_addInterceptor(self):
        setHostId('interceptorTest')
        receiver = MessageReceiver('interceptorTest')
        receiver.addInterceptor(lambda ctx, msg, clt, next_fn: next_fn())
        assert len(receiver.interceptors) == 1


# ===========================================================================
# Tests: Unit API — _deleteProxy / _deleteProxyById
# ===========================================================================

class TestDeleteProxy:
    def test_deleteProxyById(self):
        setHostId('delProxyByIdTest')
        receiver = MessageReceiver('delProxyByIdTest')
        obj = {'name': 'test'}
        receiver.getProxyManager().set(obj, 'delId1')
        assert receiver.getProxyManager().getById('delId1') is obj
        _deleteProxyById('delId1', 'delProxyByIdTest')
        assert receiver.getProxyManager().getById('delId1') is None

    def test_deleteProxy_by_reference(self):
        setHostId('delProxyTest')
        receiver = MessageReceiver('delProxyTest')
        obj = {'name': 'test'}
        receiver.getProxyManager().set(obj, 'delId2')
        assert receiver.getProxyManager().has(obj) is True
        _deleteProxy(obj, 'delProxyTest')
        assert receiver.getProxyManager().has(obj) is False


# ===========================================================================
# Tests: Stdio end-to-end
# ===========================================================================

from xuri_rpc_stdio import createServer as stdioCreateServer, createMain as stdioCreateMain

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_test_stdio_server.py')


def _write_server_script():
    script = '''\
import asyncio
import sys
sys.path.insert(0, r"{pkg_dir}")
from xuri_rpc_stdio import createServer

class ChildService:
    def add(self, a, b):
        return a + b
    def greet(self, name):
        return f'hello {{name}}'
    def echo(self, x):
        return x
    def merge(self, d):
        return {{**d, 'extra': True}}
    def boom(self):
        raise ValueError('child boom')

async def main():
    serve = await createServer('childHost')
    await serve(ChildService())

asyncio.run(main())
'''.format(pkg_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(SERVER_SCRIPT, 'w', encoding='utf-8') as f:
        f.write(script)


@pytest.fixture(scope='module', autouse=True)
def _setup_stdio_server_script():
    _write_server_script()
    yield
    if os.path.exists(SERVER_SCRIPT):
        os.remove(SERVER_SCRIPT)


@pytest.mark.asyncio
async def test_stdio_basic_call():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await stdioCreateMain('parentHost', proc.stdin, proc.stdout)
        result = await main.add(10, 20)
        assert result == 30
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_string_return():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await stdioCreateMain('parentHost', proc.stdin, proc.stdout)
        result = await main.greet('world')
        assert result == 'hello world'
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_none_handling():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await stdioCreateMain('parentHost', proc.stdin, proc.stdout)
        result = await main.echo(None)
        assert result is None
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_dict_argument_and_return():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await stdioCreateMain('parentHost', proc.stdin, proc.stdout)
        result = await main.merge({'a': 1, 'b': 2})
        assert result == {'a': 1, 'b': 2, 'extra': True}
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_exception_propagation():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await stdioCreateMain('parentHost', proc.stdin, proc.stdout)
        with pytest.raises(Exception) as exc_info:
            await main.boom()
        assert 'child boom' in str(exc_info.value)
    finally:
        proc.terminate()
        await proc.wait()


# ===========================================================================
# Tests: WebSocket end-to-end
# ===========================================================================

from xuri_rpc_websocket import createServer as wsCreateServer, createMain as wsCreateMain


class WsCalcService:
    def add(self, a: int, b: int) -> int:
        return a + b

class WsGreetService:
    def greet(self, name: str) -> str:
        return f'hello {name}'

class WsMergeService:
    def merge(self, d: Dict[str, Any]) -> Dict[str, Any]:
        return {**d, 'extra': True}

class WsEchoService:
    def echo(self, x: Any) -> Any:
        return x

class WsComputeService:
    def compute(self, a: int, b: int, cb: Callable[[int], Any]) -> int:
        return (cb(a * b), a * b)[1]

class WsBoomService:
    def boom(self) -> None:
        raise ValueError('server boom')

class WsConcatService:
    def concat(self, a: bytes, b: bytes) -> bytes:
        return a + b


@pytest.mark.asyncio
async def test_ws_basic_call():
    serve, ws_server = await wsCreateServer('wsServer', 'localhost', 18765)
    serve_task = asyncio.ensure_future(serve(WsCalcService()))
    try:
        client, main = await wsCreateMain('wsClient', 'localhost', 18765)
        result = await main.add(10, 20)
        assert result == 30
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_string_return():
    serve, ws_server = await wsCreateServer('wsServer2', 'localhost', 18766)
    serve_task = asyncio.ensure_future(serve(WsGreetService()))
    try:
        client, main = await wsCreateMain('wsClient2', 'localhost', 18766)
        result = await main.greet('world')
        assert result == 'hello world'
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_dict_argument_and_return():
    serve, ws_server = await wsCreateServer('wsServer3', 'localhost', 18767)
    serve_task = asyncio.ensure_future(serve(WsMergeService()))
    try:
        client, main = await wsCreateMain('wsClient3', 'localhost', 18767)
        result = await main.merge({'a': 1, 'b': 2})
        assert result == {'a': 1, 'b': 2, 'extra': True}
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_none_handling():
    serve, ws_server = await wsCreateServer('wsServer4', 'localhost', 18768)
    serve_task = asyncio.ensure_future(serve(WsEchoService()))
    try:
        client, main = await wsCreateMain('wsClient4', 'localhost', 18768)
        result = await main.echo(None)
        assert result is None
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_callback():
    serve, ws_server = await wsCreateServer('wsServer5', 'localhost', 18769)
    serve_task = asyncio.ensure_future(serve(WsComputeService()))
    try:
        client, main = await wsCreateMain('wsClient5', 'localhost', 18769)
        callback_val = None
        def on_result(v):
            nonlocal callback_val
            callback_val = v
        result = await main.compute(3, 7, on_result)
        assert result == 21
        await asyncio.sleep(0.1)
        assert callback_val == 21
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_exception_propagation():
    serve, ws_server = await wsCreateServer('wsServer6', 'localhost', 18770)
    serve_task = asyncio.ensure_future(serve(WsBoomService()))
    try:
        client, main = await wsCreateMain('wsClient6', 'localhost', 18770)
        with pytest.raises(Exception) as exc_info:
            await main.boom()
        assert 'server boom' in str(exc_info.value)
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_bytes_transfer():
    serve, ws_server = await wsCreateServer('wsServer7', 'localhost', 18771)
    serve_task = asyncio.ensure_future(serve(WsConcatService()))
    try:
        client, main = await wsCreateMain('wsClient7', 'localhost', 18771)
        a = struct.pack('>i', 42)
        b = struct.pack('>i', 99)
        result = await main.concat(a, b)
        assert struct.unpack('>i', result[:4])[0] == 42
        assert struct.unpack('>i', result[4:])[0] == 99
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


# ===========================================================================
# Tests: Direct demo (original rpc_test)
# ===========================================================================

class _DirectSender(ISender):
    def __init__(self, client: Client) -> None:
        self.client: Client = client

    async def send(self, message: RpcMessage) -> None:
        await getMessageReceiver().onReceiveMessage(message, self.client)


@pytest.mark.asyncio
async def test_direct_demo():
    setHostId('frontJs')
    getMessageReceiver().setMain(_HelloService())
    client = Client()
    client.setSender(lambda: _DirectSender(client))
    rpc = await client.getMain()
    result = await rpc.hello(1, 2, lambda a: None)
    assert result == 3
