"""test_context2.py — 拦截器链测试 (mirrors context2.test.ts)"""
import pytest
from xuri_rpc.rpc import (
    Client, MessageReceiver, setHostId, asProxy, getMessageReceiver,
)


class DirectSender:
    def __init__(self, client_callback: Client, msg_receiver: MessageReceiver):
        self.client_callback = client_callback
        self.msg_receiver = msg_receiver

    async def send(self, message: dict):
        await self.msg_receiver.onReceiveMessage(message, self.client_callback)


class MainService:
    def hello(self, a, b, on_result):
        return (on_result(a + b), a + b)[1]

    def getObject(self):
        return asProxy(
            SayService(), 'backendJs'
        )


class SayService:
    def say(self, name):
        print('hello ', name)


class ContextTestService:
    def hello(self, context):
        return f"hello {context.get('a')} and {context.get('b')}"


@pytest.mark.asyncio
async def test_interceptor_chain():
    setHostId('frontJs')
    hostId = 'backendJs'

    messageReceiver_backend = MessageReceiver(hostId)

    messageReceiver_backend.setMain(MainService())
    messageReceiver_backend.setObject(
        'contextTest',
        ContextTestService(),
        True,
    )
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
    client.sender = sender
    client_on_backend.sender = back_sender
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.get_object('contextTest')
    result = await rpc.hello()
    assert result == 'hello mike and jack'
