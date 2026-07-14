"""test_context.py — 拦截器上下文测试 (mirrors context.test.ts)"""
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
        return 'hello'


@pytest.mark.asyncio
async def test_context_object():
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

    client = Client()
    client_on_backend = Client(hostId)
    sender = DirectSender(client_on_backend, messageReceiver_backend)
    back_sender = DirectSender(client, getMessageReceiver())
    client.sender = sender
    client_on_backend.sender = back_sender
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.get_object('contextTest')
    result = await rpc.hello()
    assert result == 'hello'
