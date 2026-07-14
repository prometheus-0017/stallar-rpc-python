"""test_websocket.py — WebSocket 二进制通信端到端测试"""
import asyncio
import struct
import pytest

from xuri_rpc_websocket import createServer, createMain


# ---------------------------------------------------------------------------
# Service classes exposed as the main object (not dicts)
# ---------------------------------------------------------------------------

class CalculatorService:
    def add(self, a, b):
        return a + b


class GreetService:
    def greet(self, name):
        return f'hello {name}'


class MergeService:
    def merge(self, d):
        return {**d, 'extra': True}


class EchoService:
    def echo(self, x):
        return x


class ComputeService:
    def compute(self, a, b, cb):
        return (cb(a * b), a * b)[1]


class BoomService:
    def boom(self):
        raise ValueError('server boom')


class ConcatService:
    def concat(self, a, b):
        return a + b


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ws_basic_call():
    """Server exposes add, client calls it over WebSocket."""
    serve, ws_server = await createServer('wsServer', 'localhost', 18765)
    serve_task = asyncio.ensure_future(serve(CalculatorService()))

    try:
        client, main = await createMain('wsClient', 'localhost', 18765)
        result = await main.add(10, 20)
        assert result == 30
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_string_return():
    serve, ws_server = await createServer('wsServer2', 'localhost', 18766)
    serve_task = asyncio.ensure_future(serve(GreetService()))

    try:
        client, main = await createMain('wsClient2', 'localhost', 18766)
        result = await main.greet('world')
        assert result == 'hello world'
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_dict_argument_and_return():
    serve, ws_server = await createServer('wsServer3', 'localhost', 18767)
    serve_task = asyncio.ensure_future(serve(MergeService()))

    try:
        client, main = await createMain('wsClient3', 'localhost', 18767)
        result = await main.merge({'a': 1, 'b': 2})
        assert result == {'a': 1, 'b': 2, 'extra': True}
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_none_handling():
    serve, ws_server = await createServer('wsServer4', 'localhost', 18768)
    serve_task = asyncio.ensure_future(serve(EchoService()))

    try:
        client, main = await createMain('wsClient4', 'localhost', 18768)
        result = await main.echo(None)
        assert result is None
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_callback():
    """Server calls a callback passed from the client."""
    serve, ws_server = await createServer('wsServer5', 'localhost', 18769)
    serve_task = asyncio.ensure_future(serve(ComputeService()))

    try:
        client, main = await createMain('wsClient5', 'localhost', 18769)

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
    serve, ws_server = await createServer('wsServer6', 'localhost', 18770)
    serve_task = asyncio.ensure_future(serve(BoomService()))

    try:
        client, main = await createMain('wsClient6', 'localhost', 18770)
        with pytest.raises(Exception) as exc_info:
            await main.boom()
        assert 'server boom' in str(exc_info.value)
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task


@pytest.mark.asyncio
async def test_ws_bytes_transfer():
    """Binary data (bytes) round-trip through WebSocket + CBOR."""
    serve, ws_server = await createServer('wsServer7', 'localhost', 18771)
    serve_task = asyncio.ensure_future(serve(ConcatService()))

    try:
        client, main = await createMain('wsClient7', 'localhost', 18771)
        a = struct.pack('>i', 42)
        b = struct.pack('>i', 99)
        result = await main.concat(a, b)
        assert struct.unpack('>i', result[:4])[0] == 42
        assert struct.unpack('>i', result[4:])[0] == 99
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await serve_task
