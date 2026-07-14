"""
xuri-rpc: Python version of the RPC framework.
Core module containing all RPC logic.
"""
import abc
import asyncio
import weakref
import time
import traceback
from typing import (
    Any, Optional, Callable, Dict, List, Set, Union, Tuple,
)

# ---------------------------------------------------------------------------
# Types & constants
# ---------------------------------------------------------------------------

ArgObjType = Optional[str]  # 'proxy' | 'data' | 'datetime' | None

# Type alias for RPC message dicts
RpcMessage = Dict[str, Any]

debugFlag: bool = False
_hostId: Optional[str] = None
_idCount: int = 0
_enhanceType: bool = True

_gcTimeLimit: float = 30.0        # seconds
_connectionLimit: float = 30.0     # seconds

_DEFAULT_HOST_KEY: str = '__default_host__'


def setDebugFlag(flag: bool) -> None:
    global debugFlag
    debugFlag = flag


def _getId(hostId: Optional[str] = None) -> str:
    global _idCount
    hid = hostId if hostId is not None else _hostId
    rid = f"{hid}{_idCount}"
    _idCount += 1
    return rid


# ---------------------------------------------------------------------------
# PreArgObj
# ---------------------------------------------------------------------------

class PreArgObj:
    """Wrapper that marks an argument as a proxy reference or plain data."""

    def __init__(self, argType: ArgObjType, data: Any) -> None:
        self.type: ArgObjType = argType
        self.data: Any = data


# ---------------------------------------------------------------------------
# ISender abstract base class
# ---------------------------------------------------------------------------

class ISender(abc.ABC):
    """Abstract base class for message senders. Implementations may be sync or async."""

    @abc.abstractmethod
    async def send(self, message: RpcMessage) -> None:
        ...


# ---------------------------------------------------------------------------
# Proxy managers
# ---------------------------------------------------------------------------

class _ProxyObjectHandler:
    """Internal handler that stores a proxy object reference with metadata."""

    def __init__(self, objId: str, target: Any) -> None:
        self.id: str = objId
        self.target: Any = target
        self.lastRegistered: float = time.time()


class ObjectOfProxyManager:
    """Manages local objects exposed as proxies (object -> id mapping)."""

    def __init__(self) -> None:
        self.proxyMap: Dict[int, str] = {}          # id(obj) -> id
        self.reverseProxyMap: Dict[str, _ProxyObjectHandler] = {}  # id -> handler
        self._objRefs: Dict[int, Any] = {}           # keep strong refs to prevent GC

    def set(self, obj: Any, objId: str) -> None:
        self.proxyMap[id(obj)] = objId
        self.reverseProxyMap[objId] = _ProxyObjectHandler(objId, obj)
        self._objRefs[id(obj)] = obj

    def reRegister(self, objId: str) -> None:
        handler = self.reverseProxyMap.get(objId)
        if handler:
            handler.lastRegistered = time.time()

    def getById(self, objId: str) -> Any:
        handler = self.reverseProxyMap.get(objId)
        return handler.target if handler else None

    def get(self, obj: Any) -> Optional[str]:
        return self.proxyMap.get(id(obj))

    def has(self, obj: Any) -> bool:
        return id(obj) in self.proxyMap

    def deleteById(self, objId: str) -> None:
        handler = self.reverseProxyMap.get(objId)
        if handler:
            self.proxyMap.pop(id(handler.target), None)
            self._objRefs.pop(id(handler.target), None)
            del self.reverseProxyMap[objId]

    def delete(self, obj: Any) -> None:
        objId = self.proxyMap.get(id(obj))
        if objId is not None:
            self.reverseProxyMap.pop(objId, None)
            del self.proxyMap[id(obj)]
            self._objRefs.pop(id(obj), None)


class RemoteProxyManager:
    """Manages remote proxy objects received from the other side (id -> weakref)."""

    def __init__(self) -> None:
        self.map: Dict[str, 'weakref.ref[Any]'] = {}
        self.clientMap: Dict['Client', Set[str]] = {}

    def set(self, objId: str, proxy: Any, client: 'Client') -> None:
        self.map[objId] = weakref.ref(proxy)
        if client not in self.clientMap:
            self.clientMap[client] = set()
        self.clientMap[client].add(objId)

    def get(self, objId: str) -> Any:
        ref = self.map.get(objId)
        if ref is None:
            return None
        result = ref()
        if result is None:
            del self.map[objId]
            return None
        return result


# ---------------------------------------------------------------------------
# Helper: proxy descriptor creation
# ---------------------------------------------------------------------------

def _createProxyForObject(proxyId: str, obj: Any, hostIdVal: str) -> Optional[RpcMessage]:
    """Create a ProxyDescriber dict for a local object."""
    if callable(obj) and not isinstance(obj, dict):
        return {
            'id': proxyId,
            'hostId': hostIdVal,
            'members': [{'type': 'function', 'name': '__call__'}],
        }
    if obj is None:
        return None

    # dict 作为 Record（键值映射），遍历其键来生成成员描述
    if isinstance(obj, dict):
        members = []
        for key in obj:
            if not isinstance(key, str):
                continue
            if key.startswith('__'):
                continue
            val = obj[key]
            if callable(val):
                members.append({'name': key, 'type': 'function'})
        return {
            'id': proxyId,
            'hostId': hostIdVal,
            'members': members,
        }

    # 普通对象：遍历其属性和方法
    members = []
    for name in dir(obj):
        if name.startswith('__'):
            continue
        try:
            if callable(getattr(obj, name)):
                members.append({'name': name, 'type': 'function'})
        except AttributeError:
            continue
    return {
        'id': proxyId,
        'hostId': hostIdVal,
        'members': members,
    }


def _getOrGenerateObjectId(obj: Any, hostIdFrom: Optional[str]) -> str:
    proxyManager: ObjectOfProxyManager = _getOrCreateOption(hostIdFrom)['objectOfProxyManager']
    hostVal: Optional[str] = _getOrCreateOption(hostIdFrom)['hostId']
    if hostVal is None:
        raise ValueError("hostId is null")
    if not proxyManager.has(obj):
        newId = _getId(hostVal)
        proxyManager.set(obj, newId)
    return proxyManager.get(obj)


def asProxy(obj: Any, hostIdFrom: Optional[str] = None) -> PreArgObj:
    """Register *obj* as a proxy and return a PreArgObj describing it."""
    opt = _getOrCreateOption(hostIdFrom)
    hid = opt['hostId']
    objId = _getOrGenerateObjectId(obj, hid)
    proxy = _createProxyForObject(objId, obj, hid)
    return PreArgObj('proxy', proxy)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def generateErrorReply(message: RpcMessage, errorText: str, status: int = 500, hostId: Optional[str] = None) -> RpcMessage:
    return {
        'id': _getId(hostId),
        'idFor': message['id'],
        'meta': {},
        'trace': errorText,
        'status': status,
    }


# ---------------------------------------------------------------------------
# Type-check helpers
# ---------------------------------------------------------------------------

def _isDict(obj: Any) -> bool:
    return isinstance(obj, dict)


def _isSimpleObject(obj: Any) -> bool:
    return isinstance(obj, (bytes, str, int, float, bool, type(None)))


# ---------------------------------------------------------------------------
# ArgTranslator
# ---------------------------------------------------------------------------

class ICustomTranslator(abc.ABC):
    """Abstract base class for custom argument translators."""

    @abc.abstractmethod
    def match(self, obj: Any) -> bool:
        ...

    @abc.abstractmethod
    def translate(self, obj: Any) -> Any:
        ...

    @abc.abstractmethod
    def reverseTranslate(self, obj: Any) -> Any:
        ...


class ArgTranslator:
    """Translates arguments to/from serialisable ArgObj dicts."""

    def __init__(self) -> None:
        self.typeIndicator: str = '__is_rpc_proxy__'
        self.customTranslators: List[ICustomTranslator] = []

    def setTypeIndicator(self, indicator: str) -> None:
        self.typeIndicator = indicator

    # -- local -> remote --------------------------------------------------

    def toArgObj(self, target: Any, asProxyLocal: Callable[[Any], PreArgObj]) -> Any:
        if target is None:
            return None

        def _handlePreArgObj(obj: PreArgObj) -> Any:
            obj.data[self.typeIndicator] = self.typeIndicator
            return obj.data

        if isinstance(target, PreArgObj):
            if target.type == 'proxy':
                return _handlePreArgObj(target)
            elif target.type == 'data':
                return target.data
            else:
                raise NotImplementedError("type not implemented")

        if _isSimpleObject(target):
            return target

        if isinstance(target, list):
            return [self.toArgObj(item, asProxyLocal) for item in target]

        if _isDict(target):
            return {k: self.toArgObj(v, asProxyLocal) for k, v in target.items()}

        for ct in self.customTranslators:
            if ct.match(target):
                return ct.translate(target)

        preObj = asProxyLocal(target)
        return _handlePreArgObj(preObj)

    # -- remote -> local --------------------------------------------------

    def reverseToArgObj(self, target: Any, client: 'Client') -> Any:
        if _isDict(target) and self.typeIndicator in target:
            data = target
            result = client.createRemoteProxy(data)
            client.getRunnableProxyManager().set(data['id'], result, client)
            return result

        for ct in self.customTranslators:
            if hasattr(target, 'data') and ct.match(target.get('data')):
                return ct.reverseTranslate(target['data'])

        if isinstance(target, list):
            return [self.reverseToArgObj(item, client) for item in target]

        if _isDict(target):
            return {k: self.reverseToArgObj(v, client) for k, v in target.items()}

        return target


# ---------------------------------------------------------------------------
# AutoWrapper
# ---------------------------------------------------------------------------

def _shallowAutoWrapper(obj: Any) -> Any:
    """Default auto-wrapper: returns the object unchanged."""
    return obj


AutoWrapper = Callable[[Any], Any]


# ---------------------------------------------------------------------------
# RemoteProxy – Python equivalent of a JS dynamic proxy object
# ---------------------------------------------------------------------------

class RemoteProxy:
    """Dynamic proxy object that forwards method calls to the remote side."""

    def __init__(self) -> None:
        self._methods: Dict[str, Callable[..., Any]] = {}
        self._isCallable: bool = False

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._isCallable and '__call__' in self._methods:
            return self._methods['__call__'](*args, **kwargs)
        raise TypeError("This remote proxy is not callable")

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        methods = object.__getattribute__(self, '_methods')
        if name in methods:
            return methods[name]
        raise AttributeError(f"No remote method '{name}'")

    def addMethod(self, name: str, func: Callable[..., Any]) -> None:
        """Register a remote method."""
        self._methods[name] = func
        if name == '__call__':
            self._isCallable = True


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class Client:
    """RPC client that sends requests and receives responses via an ISender."""

    def __init__(self, hostIdVal: Optional[str] = None) -> None:
        self.hostId: Optional[str] = hostIdVal
        self._useSender: Callable[[], Optional[ISender]] = lambda: None
        self.argTranslator: ArgTranslator = ArgTranslator()
        self.argsAutoWrapper: AutoWrapper = _shallowAutoWrapper

    # -- configuration ----------------------------------------------------

    def setSender(self, useSender: Callable[[], Optional[ISender]]) -> None:
        self._useSender = useSender

    def useSender(self) -> Optional[ISender]:
        return self._useSender()

    def setArgsAutoWrapper(self, wrapper: AutoWrapper) -> None:
        self.argsAutoWrapper = wrapper

    # -- internal helpers -------------------------------------------------

    def _getReqPending(self) -> Dict[str, Any]:
        return _getOrCreateOption(self.hostId)['requestPendingDict']

    def _putAwait(self, reqId: str, future: 'asyncio.Future[Any]', request: RpcMessage) -> None:
        self._getReqPending()[reqId] = {
            'future': future,
            'request': request,
            'sendTime': time.time(),
        }
    def getSessionData(self) -> dict[str,Any]:
        return _getOrCreateOption(self.hostId)['session']

    def getHostId(self) -> Optional[str]:
        if self.hostId is None:
            return _getOrCreateOption(None)['hostId']
        return self.hostId

    def getProxyManager(self) -> ObjectOfProxyManager:
        return _getOrCreateOption(self.hostId)['objectOfProxyManager']

    def getRunnableProxyManager(self) -> RemoteProxyManager:
        return _getOrCreateOption(self.hostId)['runnableProxyManager']

    # -- public API -------------------------------------------------------

    def toArgObj(self, obj: Any) -> Any:
        return self.argTranslator.toArgObj(
            obj, lambda o: asProxy(o, self.getHostId())
        )

    async def waitForRequest(self, request: RpcMessage) -> Any:
        if debugFlag:
            print(
                f"{self.getHostId()} is waiting for {request['id']},", request
            )
        sender = self.useSender()
        if sender is None:
            raise RuntimeError("sender not set")

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._putAwait(request['id'], future, request)

        try:
            result = sender.send(request)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result
        except Exception as e:
            if not future.done():
                future.set_exception(e)

        return await future

    def createRemoteProxy(self, data: RpcMessage) -> Any:
        """Build a RemoteProxy (or return cached) from a ProxyDescriber dict."""
        if data.get('hostId') == self.hostId:
            return self.getProxyManager().getById(data['id'])

        cached = self.getRunnableProxyManager().get(data['id'])
        if cached is not None:
            return cached

        proxy = RemoteProxy()
        for member in data.get('members', []):
            memberType = member.get('type')
            memberName = member.get('name')

            if memberType == 'property':
                print("property proxy not implemented")
            elif memberType == 'function':
                _dataId = data['id']
                _methodName = memberName

                async def _remoteCall(*args, _did=_dataId, _mn=_methodName):
                    argsTransformed = [
                        self.toArgObj(self.argsAutoWrapper(a)) for a in args
                    ]
                    request = {
                        'objectId': _did,
                        'meta': {},
                        'id': _getId(self.hostId),
                        'method': _mn,
                        'args': argsTransformed,
                    }
                    return await self.waitForRequest(request)

                proxy.addMethod(memberName, _remoteCall)

        return proxy

    def transformArg(self, argObj: RpcMessage, clazz: Any = None) -> Any:
        if argObj.get('type') == 'data':
            return argObj['data']
        data = argObj['data']
        result = self.createRemoteProxy(data)
        self.getRunnableProxyManager().set(data['id'], result, self)
        return result

    def reverseToArgObj(self, argObj: Any) -> Any:
        return self.argTranslator.reverseToArgObj(argObj, self)

    async def getObject(self, objectId: str) -> Any:
        request = {
            'meta': {},
            'id': _getId(self.hostId),
            'objectId': 'main0',
            'method': 'getMain',
            'args': [self.toArgObj(objectId)],
        }
        return await self.waitForRequest(request)

    async def getMain(self) -> Any:
        return await self.getObject('main')


# ---------------------------------------------------------------------------
# Options (per-host state)
# ---------------------------------------------------------------------------

class _MessageReceiverOptions:
    """Internal per-host-id state container (stored as a dict)."""
    pass


_options: Dict[str, Dict[str, Any]] = {}


def _getOrCreateOption(
    hostIdVal: Optional[str] = None,
) -> Dict[str, Any]:
    key: str = hostIdVal if hostIdVal is not None else _DEFAULT_HOST_KEY
    if key == _hostId:
        key = _DEFAULT_HOST_KEY
    if key not in _options:
        _options[key] = {
            'objectOfProxyManager': ObjectOfProxyManager(),
            'runnableProxyManager': RemoteProxyManager(),
            'session':{},
            'hostId': None if key == _DEFAULT_HOST_KEY else key,
            'requestPendingDict': {},
        }
    return _options[key]


def setHostId(hid: str) -> None:
    global _hostId
    _hostId = hid
    _getOrCreateOption(None)['hostId'] = hid


def _deleteProxyById(objId: str, hostIdVal: Optional[str] = None) -> None:
    """Remove a proxy from the manager by its id."""
    _getOrCreateOption(hostIdVal)['objectOfProxyManager'].deleteById(objId)


def _deleteProxy(obj: Any, hostIdVal: Optional[str] = None) -> None:
    """Remove a proxy from the manager by object reference."""
    _getOrCreateOption(hostIdVal)['objectOfProxyManager'].delete(obj)


# ---------------------------------------------------------------------------
# MessageReceiver
# ---------------------------------------------------------------------------

class MessageReceiver:
    """Receives and dispatches RPC messages (both requests and responses)."""

    def __init__(self, hostIdVal: Optional[str] = None) -> None:
        self.hostId: Optional[str] = hostIdVal
        self.rpcServer: Optional[Any] = None
        self.interceptors: List[Callable[..., Any]] = []
        self.objectWithContext: Set[str] = set()
        self.resultAutoWrapper: AutoWrapper = _shallowAutoWrapper

        # Register the built-in 'main0' handler object
        hostIdToSend = self.getHostId()

        def _getMain(objectId: str = None):
            if objectId is None:
                objectId = 'main'
            return asProxy(
                self.getProxyManager().getById(objectId), hostIdToSend
            )

        def _reRegister(lst: list):
            for item in lst:
                objId = item[0]
                self.getProxyManager().reRegister(objId)

        self.getProxyManager().set(
            {'getMain': _getMain, 'reRegister': _reRegister}, 'main0'
        )

    # -- helpers ----------------------------------------------------------

    def getProxyManager(self) -> ObjectOfProxyManager:
        return _getOrCreateOption(self.hostId)['objectOfProxyManager']

    def getRunnableProxyManager(self) -> RemoteProxyManager:
        return _getOrCreateOption(self.hostId)['runnableProxyManager']

    def getHostId(self) -> Optional[str]:
        return _getOrCreateOption(self.hostId)['hostId']

    def getReqPending(self) -> Dict[str, Any]:
        return _getOrCreateOption(self.hostId)['requestPendingDict']

    # -- configuration ----------------------------------------------------

    def setMain(self, obj: Any) -> None:
        self.rpcServer = obj
        self.setObject('main', self.rpcServer, False)

    def setObject(self, objId: str, obj: Any, withContext: bool) -> None:
        self.getProxyManager().set(obj, objId)
        if withContext:
            self.objectWithContext.add(objId)

    def addInterceptor(self, interceptor: Callable[..., Any]) -> None:
        self.interceptors.append(interceptor)

    def setResultAutoWrapper(self, wrapper: AutoWrapper) -> None:
        self.resultAutoWrapper = wrapper

    def currentWaitingCount(self) -> int:
        return len(self.getReqPending())

    # -- interceptor chain ------------------------------------------------

    async def withContext(
        self, message: RpcMessage, client: Client, args: List[Any], func: Callable[..., Any]
    ) -> Any:
        resultContainer: Dict[str, Any] = {}

        context = {
            'setContext': lambda r: resultContainer.__setitem__('value', r),
        }

        def generateInterceptorExecutor(index: int) -> Callable:
            if index < len(self.interceptors):
                async def executeThis():
                    interceptor = self.interceptors[index]

                    async def generateAndExecuteNext():
                        executor = generateInterceptorExecutor(index + 1)
                        await executor()

                    await interceptor(context, message, client, generateAndExecuteNext)

                return executeThis
            else:
                async def executeFinal():
                    r = func(context, *args)
                    if asyncio.iscoroutine(r) or asyncio.isfuture(r):
                        r = await r
                    resultContainer['value'] = r

                return executeFinal

        first = generateInterceptorExecutor(0)
        await first()
        return resultContainer.get('value')

    # -- core message handling -------------------------------------------

    async def onReceiveMessage(self, messageRecv: RpcMessage, clientForCallback: Client) -> None:
        if clientForCallback is None:
            raise ValueError("clientForCallback must not be None")
        if not isinstance(clientForCallback, Client):
            raise TypeError("clientForCallback must be a Client")

        if debugFlag:
            idFor = messageRecv.get('idFor')
            if idFor:
                print(
                    f"{self.getHostId()} received a reply for {idFor}",
                    messageRecv,
                )
            else:
                print(
                    f"{self.getHostId()} received a request, id={messageRecv.get('id')}",
                    messageRecv,
                )

        # ----- REQUEST -----
        if not _isResponse(messageRecv):
            message = messageRecv
            try:
                obj = self.getProxyManager().getById(message['objectId'])
                if obj is None:
                    _maybeAwait(
                        clientForCallback.useSender().send(
                            generateErrorReply(message, 'object not found', 100, self.hostId)
                        )
                    )
                    return

                args = [clientForCallback.reverseToArgObj(a) for a in message['args']]

                shouldWithContext = message['objectId'] in self.objectWithContext

                if message['method'] == '__call__':
                    if shouldWithContext:
                        result = await self.withContext(
                            message, clientForCallback, args, obj
                        )
                    else:
                        result = obj(*args)
                else:
                    if isinstance(obj, dict):
                        methodFunc = obj[message['method']]
                    else:
                        methodFunc = getattr(obj, message['method'])
                    if shouldWithContext:
                        result = await self.withContext(
                            message, clientForCallback, args, methodFunc
                        )
                    else:
                        result = methodFunc(*args)

                result = self.resultAutoWrapper(result)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    result = await result

                wrappedResult = clientForCallback.toArgObj(result)

                reply = {
                    'id': _getId(self.hostId),
                    'objectId': '',
                    'method': '',
                    'args': [],
                    'meta': {},
                    'idFor': message['id'],
                    'data': wrappedResult,
                    'status': 200,
                }
                _maybeAwait(clientForCallback.useSender().send(reply))

            except Exception as e:
                traceStr = traceback.format_exc()
                errorReply = {
                    'id': _getId(self.hostId),
                    'objectId': '',
                    'method': '',
                    'args': [],
                    'meta': {},
                    'idFor': message['id'],
                    'data': {'type': 'data', 'data': None},
                    'trace': traceStr,
                    'status': -1,
                }
                if clientForCallback.useSender():
                    _maybeAwait(clientForCallback.useSender().send(errorReply))
                print(f"Error handling request: {e}")

        # ----- RESPONSE -----
        else:
            idFor = messageRecv['idFor']
            message = messageRecv
            reqPending = self.getReqPending()

            if idFor not in reqPending:
                print(
                    f"[{self.getHostId()}] no pending request for id {idFor}",
                    message,
                )
                return

            req = reqPending.pop(idFor)
            future: asyncio.Future = req['future']

            if message['status'] == 200:
                if not future.done():
                    future.set_result(
                        clientForCallback.reverseToArgObj(message['data'])
                    )
            else:
                if not future.done():
                    future.set_exception(RpcRemoteError(message))


class RpcRemoteError(Exception):
    """Raised when the remote side returns a non-200 status."""

    def __init__(self, response: RpcMessage) -> None:
        self.response: RpcMessage = response
        trace: str = response.get('trace', '')
        super().__init__(f"Remote error (status={response.get('status')}): {trace}")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _isResponse(message: RpcMessage) -> bool:
    return message.get('idFor') is not None


def _maybeAwait(result: Any) -> None:
    """Fire-and-forget for sender calls that may return a coroutine."""
    if asyncio.iscoroutine(result):
        asyncio.ensure_future(result)


# ---------------------------------------------------------------------------
# Singleton message receiver
# ---------------------------------------------------------------------------

_messageReceiver: Optional[MessageReceiver] = None


def getMessageReceiver() -> MessageReceiver:
    global _messageReceiver
    if _messageReceiver is None:
        _messageReceiver = MessageReceiver()
    return _messageReceiver


# ---------------------------------------------------------------------------
# Maintenance / GC helpers
# ---------------------------------------------------------------------------

def removeOutdatedProxyObject(timeout: float = -1) -> None:
    if timeout <= 0:
        timeout = _gcTimeLimit
    for k, opt in _options.items():
        manager: ObjectOfProxyManager = opt['objectOfProxyManager']
        before = len(manager.proxyMap)
        count = 0
        toDelete = []
        for objId, handler in manager.reverseProxyMap.items():
            if objId == 'main0':
                continue
            if time.time() - handler.lastRegistered > timeout * 3:
                toDelete.append(objId)
                count += 1
        for objId in toDelete:
            manager.deleteById(objId)
        if count > 0 and debugFlag:
            print(
                f"{k} removed {count} proxies, before {before} "
                f"after {len(manager.proxyMap)}"
            )


def getProxyHoldingInfo() -> List[Dict[str, Any]]:
    result = []
    for opt in _options.values():
        manager: ObjectOfProxyManager = opt['objectOfProxyManager']
        earliest = time.time()
        for objId, handler in manager.reverseProxyMap.items():
            if handler is None or objId == 'main0':
                continue
            if handler.lastRegistered < earliest:
                earliest = handler.lastRegistered
        result.append({
            'hostId': opt['hostId'],
            'count': len(manager.proxyMap),
            'earliestDate': earliest,
        })
    result.sort(key=lambda x: x['count'])
    return result


async def autoReRegister() -> None:
    for opt in _options.values():
        manager: RemoteProxyManager = opt['runnableProxyManager']
        for client, ids in list(manager.clientMap.items()):
            toReRegister = []
            for objId in list(ids):
                obj = manager.get(objId)
                if obj is None:
                    ids.discard(objId)
                    if len(ids) == 0:
                        del manager.clientMap[client]
                    continue
                toReRegister.append([objId])

            request = {
                'meta': {},
                'id': _getId(opt['hostId']),
                'objectId': 'main0',
                'method': 'reRegister',
                'args': [client.toArgObj(toReRegister)],
            }
            await client.waitForRequest(request)


def _killTimeoutConnection(
    client: Optional[Client] = None, millisec: float = -1
) -> None:
    if millisec == -1:
        millisec = _connectionLimit

    def _forOptions(func):
        if client is not None:
            func(_getOrCreateOption(client.getHostId()))
        else:
            for opt in _options.values():
                func(opt)

    def _check(opt):
        reqPending = opt['requestPendingDict']
        toDelete = []
        for reqId, value in reqPending.items():
            if time.time() - value['sendTime'] > millisec:
                future = value['future']
                if not future.done():
                    future.set_exception(TimeoutError("timeout"))
                toDelete.append(reqId)
        for reqId in toDelete:
            del reqPending[reqId]

    _forOptions(_check)


async def autoCheck() -> None:
    """Start periodic maintenance tasks (GC, timeout killing, re-registration)."""

    async def _periodic(func: Callable[..., Any], interval: float = 3.0) -> None:
        while True:
            await asyncio.sleep(interval)
            result = func()
            if asyncio.iscoroutine(result):
                await result

    asyncio.ensure_future(_periodic(_killTimeoutConnection))
    asyncio.ensure_future(_periodic(autoReRegister))
    asyncio.ensure_future(_periodic(removeOutdatedProxyObject))
