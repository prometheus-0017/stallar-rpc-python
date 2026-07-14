"""test_error_handling.py — 错误处理测试 (mirrors error_handling.test.ts)"""
import pytest
from xuri_rpc.rpc import (
    Client, MessageReceiver, setHostId, generateErrorReply, asProxy,
)


class DirectSender:
    """Test sender that dispatches directly to a MessageReceiver."""

    def __init__(self, client_callback: Client, msg_receiver: MessageReceiver):
        self.client_callback = client_callback
        self.msg_receiver = msg_receiver

    async def send(self, message: dict):
        await self.msg_receiver.onReceiveMessage(message, self.client_callback)


@pytest.mark.asyncio
async def test_setSender_called_twice_raises():
    client = Client()
    client.setSender(DirectSender(client, MessageReceiver()))
    with pytest.raises(RuntimeError, match='sender already set'):
        client.setSender(DirectSender(client, MessageReceiver()))


@pytest.mark.asyncio
async def test_onReceiveMessage_null_client():
    receiver = MessageReceiver('errTestNull')
    with pytest.raises(ValueError, match='client_for_callback must not be None'):
        await receiver.onReceiveMessage(
            {'id': 'test', 'idFor': None, 'meta': {}, 'status': 200}, None
        )


@pytest.mark.asyncio
async def test_onReceiveMessage_non_client():
    receiver = MessageReceiver('errTestNonClient')
    with pytest.raises(TypeError, match='client_for_callback must be a Client'):
        await receiver.onReceiveMessage(
            {'id': 'test', 'idFor': None, 'meta': {}, 'status': 200}, object()
        )


class NotFoundService:
    def hello(self):
        return 'world'


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
    client.sender = sender
    client_on_backend.sender = back_sender
    client.setArgsAutoWrapper(lambda x: x)

    error_caught = False
    try:
        await client.wait_for_request({
            'id': 'testReq1',
            'objectId': 'nonExistentObj',
            'method': 'someMethod',
            'args': [],
            'meta': {},
        })
    except Exception as e:
        error_caught = True
        assert e.response['status'] == 100
        assert e.response['trace'] == 'object not found'
    assert error_caught


def test_generateErrorReply():
    request = {
        'id': 'req123', 'meta': {}, 'method': 'testMethod',
        'objectId': 'obj1', 'args': [],
    }
    reply = generateErrorReply(request, 'something went wrong', 500)
    assert reply['idFor'] == 'req123'
    assert reply['status'] == 500
    assert reply['trace'] == 'something went wrong'
    assert 'meta' in reply


def test_generateErrorReply_default_status():
    request = {
        'id': 'req456', 'meta': {}, 'method': 'testMethod',
        'objectId': 'obj1', 'args': [],
    }
    reply = generateErrorReply(request, 'default error')
    assert reply['status'] == 500


class ExceptionThrowService:
    def throwErr(self):
        raise Exception('server error')


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
    client.sender = sender
    client_on_backend.sender = back_sender
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
