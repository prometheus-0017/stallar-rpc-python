"""test_unit_api.py — 单元测试 (mirrors unit_api.test.ts)"""
import pytest
from xuri_rpc import (
    Client, MessageReceiver, PreArgObj, setHostId,
    PlainProxyManager, RunnableProxyManager,
    _deleteProxy, _deleteProxyById,
)


# ---------------------------------------------------------------------------
# ObjectOfProxyManager (PlainProxyManager)
# ---------------------------------------------------------------------------

class TestPlainProxyManager:
    def test_set_and_get_by_id(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id1')
        assert manager.get_by_id('id1') is obj
        assert manager.get(obj) == 'id1'
        assert manager.has(obj) is True

    def test_delete_by_reference(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id2')
        assert manager.has(obj) is True
        manager.delete(obj)
        assert manager.has(obj) is False
        assert manager.get_by_id('id2') is None

    def test_delete_by_id(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id3')
        manager.delete_by_id('id3')
        assert manager.has(obj) is False
        assert manager.get_by_id('id3') is None

    def test_handle_multiple_objects(self):
        manager = PlainProxyManager()
        obj1 = {'name': 'a'}
        obj2 = {'name': 'b'}
        manager.set(obj1, 'id1')
        manager.set(obj2, 'id2')
        assert manager.get(obj1) == 'id1'
        assert manager.get(obj2) == 'id2'
        assert manager.get_by_id('id1') is obj1
        assert manager.get_by_id('id2') is obj2

    def test_overwrite_with_same_id(self):
        manager = PlainProxyManager()
        obj1 = {'name': 'a'}
        obj2 = {'name': 'b'}
        manager.set(obj1, 'id1')
        manager.set(obj2, 'id1')
        assert manager.get_by_id('id1') is obj2

    def test_re_register_updates_last_registered(self):
        manager = PlainProxyManager()
        obj = {'name': 'test'}
        manager.set(obj, 'id1')
        before = manager.reverse_proxy_map['id1'].last_registered
        import time
        time.sleep(0.01)
        manager.re_register('id1')
        after = manager.reverse_proxy_map['id1'].last_registered
        assert after >= before


# ---------------------------------------------------------------------------
# RemoteProxyManager (RunnableProxyManager)
# ---------------------------------------------------------------------------

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
        assert client in manager.client_map
        assert 'id1' in manager.client_map[client]

    def test_multiple_proxies_for_same_client(self):
        manager = RunnableProxyManager()

        class _Proxy1:
            def method1(self): pass

        class _Proxy2:
            def method2(self): pass

        proxy1 = _Proxy1()
        proxy2 = _Proxy2()
        client = Client()
        manager.set('id1', proxy1, client)
        manager.set('id2', proxy2, client)
        assert len(manager.client_map[client]) == 2


# ---------------------------------------------------------------------------
# PreArgObj
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TestClient:
    def test_get_hostId_from_option(self):
        setHostId('unitTestHost')
        client = Client()
        assert client.get_hostId() == 'unitTestHost'

    def test_use_own_hostId(self):
        client = Client('customHost')
        assert client.get_hostId() == 'customHost'


# ---------------------------------------------------------------------------
# MessageReceiver
# ---------------------------------------------------------------------------

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
        proxy_manager = receiver.get_proxy_manager()
        main_obj = proxy_manager.get_by_id('main')
        assert main_obj is not None
        assert main_obj.hello() == 'world'

    def test_setObject_with_context(self):
        setHostId('setObjWithCtx')
        receiver = MessageReceiver('setObjWithCtx')
        receiver.setObject('myObj', {'doStuff': lambda: 42}, True)
        proxy_manager = receiver.get_proxy_manager()
        assert proxy_manager.get_by_id('myObj') is not None
        assert 'myObj' in receiver.object_with_context

    def test_setObject_without_context(self):
        setHostId('setObjNoCtx')
        receiver = MessageReceiver('setObjNoCtx')
        receiver.setObject('myObj2', {'doStuff': lambda: 42}, False)
        assert 'myObj2' not in receiver.object_with_context

    def test_addInterceptor(self):
        setHostId('interceptorTest')
        receiver = MessageReceiver('interceptorTest')
        receiver.addInterceptor(lambda ctx, msg, clt, next_fn: next_fn())
        assert len(receiver.interceptors) == 1


# ---------------------------------------------------------------------------
# _deleteProxy and _deleteProxyById
# ---------------------------------------------------------------------------

class TestDeleteProxy:
    def test_deleteProxyById(self):
        setHostId('delProxyByIdTest')
        receiver = MessageReceiver('delProxyByIdTest')
        obj = {'name': 'test'}
        receiver.get_proxy_manager().set(obj, 'delId1')
        assert receiver.get_proxy_manager().get_by_id('delId1') is obj
        _deleteProxyById('delId1', 'delProxyByIdTest')
        assert receiver.get_proxy_manager().get_by_id('delId1') is None

    def test_deleteProxy_by_reference(self):
        setHostId('delProxyTest')
        receiver = MessageReceiver('delProxyTest')
        obj = {'name': 'test'}
        receiver.get_proxy_manager().set(obj, 'delId2')
        assert receiver.get_proxy_manager().has(obj) is True
        _deleteProxy(obj, 'delProxyTest')
        assert receiver.get_proxy_manager().has(obj) is False
