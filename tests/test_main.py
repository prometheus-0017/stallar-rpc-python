"""test_main.py — 完整流程测试 (mirrors main.test.ts)"""
import pytest
from xuri_rpc.rpc import (
    Client, MessageReceiver, setHostId, asProxy, getMessageReceiver,
    _deleteProxy,
)


class DirectSender:
    def __init__(self, client_callback: Client, msg_receiver: MessageReceiver):
        self.client_callback = client_callback
        self.msg_receiver = msg_receiver

    async def send(self, message: dict):
        await self.msg_receiver.onReceiveMessage(message, self.client_callback)


class SayService:
    def say(self, name):
        print('hello ', name)


class MainFlowService:
    def __init__(self, hostId):
        self._hostId = hostId
        self._say_service = SayService()

    def hello(self, a, b, on_result):
        return (on_result(a + b), a + b)[1]

    def getObject(self):
        return asProxy(self._say_service, self._hostId)


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
    client.sender = sender
    client_on_backend.sender = back_sender
    client.setArgsAutoWrapper(lambda x: x)

    rpc = await client.getMain()

    # Test callback
    callback_val = None

    def callback(a):
        nonlocal callback_val
        callback_val = a

    result = await rpc.hello(1, 2, asProxy(callback))
    # Give callback task time to execute
    import asyncio
    await asyncio.sleep(0.05)
    assert callback_val == 3
    assert result == 3

    # Test getObject
    remote_object = await rpc.getObject()
    await remote_object.say('world')
