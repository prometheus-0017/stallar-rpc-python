from typing import Any, Dict, List, Optional, TypeVar, Generic, Callable, Mapping, Union, Set
import weakref
import asyncio
import uuid
from typing import TypedDict,Literal

T = TypeVar('T')
ArgObjType = Literal['proxy', 'data', None]
class dynamic_object(object):
    pass

class PreArgObj(Generic[T]):
    def __init__(self, arg_type: str, data: T):
        self.type = arg_type
        self.data = data
class ArgObj(TypedDict):
    type:ArgObjType
    data:Any

class PlainProxy(TypedDict):
    id: str
    hostId: str
    members: List[Dict[str, str]]

hostId: Optional[str] = None

def setHostId(id: str):
    global hostId
    hostId = id
    getOrCreateOption(None).hostId = id

def _deleteProxy(id: str, host_id: Optional[str] = None):
    getOrCreateOption(host_id).plainProxyManager.delete_by_id(id)

class Request(TypedDict):
    id: str
    objectId: str
    method: str
    args: List[ArgObj[Any]]

class Response(TypedDict):
    id: str
    idFor: Optional[str]
    status: Optional[int]
    trace: Optional[str]
    data: Optional[ArgObj[Any]]

Message=Union[Response,Request]
# Not = Mapping[str, Any]

class RunnableProxy:
    pass

class RunnableProxyManager:
    def __init__(self):
        self.map: Dict[str, weakref.ReferenceType[RunnableProxy]] = {}

    def set(self, id: str, proxy: RunnableProxy):
        self.map[id] = weakref.ref(proxy)

    def get(self, id: str) -> Optional[RunnableProxy]:
        ref = self.map.get(id)
        if ref is not None:
            result = ref()
            if result is None:
                del self.map[id]
            return result
        return None

class PlainProxyManager:
    def __init__(self):
        self.proxy_map: Dict[dynamic_object, str] = {}
        self.reverse_proxy_map: Dict[str, dynamic_object] = {}
        self.holding={}
        self.pythonId=id

    def set(self, obj: dynamic_object, id: str):
        self.proxy_map[self.pythonId(obj)] = id
        self.reverse_proxy_map[id] = obj
        self.holding[self.pythonId(obj)]=obj

    def getById(self, id: str) -> Optional[dynamic_object]:
        return self.reverse_proxy_map.get(id)

    def get(self, obj: dynamic_object) -> str:
        return self.proxy_map[self.pythonId(obj)]

    def has(self, obj: dynamic_object) -> bool:
        return self.pythonId(obj) in self.proxy_map

    def deleteById(self, id: str):
        obj = self.reverse_proxy_map.get(id)
        if obj is not None:
            del self.proxy_map[obj]
            del self.reverse_proxy_map[id]
            del self.holding[self.pythonId(obj)]

    def delete(self, obj: dynamic_object):
        id = self.proxy_map.get(obj)
        if id is not None:
            del self.reverse_proxy_map[id]
            del self.proxy_map[obj]
            del self.holding[self.pythonId(obj)]

def asProxy(obj: dynamic_object, host_id_from: Optional[str] = None) -> PreArgObj[Union[PlainProxy, None]]:
    option = getOrCreateOption(host_id_from)
    proxy_manager = option.plainProxyManager
    host_id = option.hostId

    if host_id is None:
        raise ValueError("hostId is null")

    if not proxy_manager.has(obj):
        id_ = getId()
        proxy_manager.set(obj, id_)

    id_ = proxy_manager.get(obj)

    if callable(obj):
        proxy: PlainProxy = {
            'id': id_,
            'hostId': host_id,
            'members': [{'type': 'function', 'name': '__call__'}]
        }
    else:
        if obj is None:
            proxy = None
        else:
            members = [
                {'name': k, 'type': 'function'}
                for k in dir(obj)
                if callable(getattr(obj, k)) and not k.startswith('__')
            ]
            proxy = {
                'id': id_,
                'hostId': host_id,
                'members': members
            }

    return PreArgObj('proxy', proxy)

def generateErrorReply(message: Request, error_text: str, status: int = 500) -> Response:
    reply: Response = {
        'id': getId(),
        'idFor': message['id'],
        'trace': error_text,
        'status': status,
        'data': None
    }
    return reply

def dict2obj(d: dict):
    obj=dynamic_object()
    for k, v in d.items():
        setattr(obj, k, v)
    return obj
class ISender:
    def send(self, message: Union[Request, Response]):
        raise NotImplementedError('Not implement')

class NotImplementSender(ISender):
    def send(self, message: Union[Request, Response]):
        raise NotImplementedError('Not implement')

class Client:
    def __init__(self, host_id: Optional[str] = None):
        self.sender: ISender = NotImplementSender()
        self.host_id = host_id
        self.args_auto_wrapper = shallowAutoWrapper

    def setArgsAutoWrapper(self, auto_wrapper: Callable[[Any], Any]):
        self.args_auto_wrapper = auto_wrapper

    def setSender(self, sender: ISender):
        if self.sender is not None:
            raise ValueError('sender already set')
        self.sender = sender

    def putAwait(self, id_: str, resolve: Callable[[Any], None], reject: Callable[[Any], None]):
        print(f"{self.getHostId()} is waiting for {id_}")
        getOrCreateOption(self.host_id).request_pending_dict[id_] = {'resolve': resolve, 'reject': reject}

    async def waitForRequest(self, request: Request) -> dynamic_object:
        sender = self.sender
        future = asyncio.Future()

        def callback(resolve, reject):
            if sender is None:
                raise ValueError('sender not set')
            self.putAwait(request['id'], resolve, reject)
            asyncio.ensure_future(sender.send(request))

        callback(future.set_result, future.set_exception)
        return await future

    def toArgObj(self, obj: Any) -> ArgObj[Any]:
        if isinstance(obj, PreArgObj):
            return dict(type='proxy',data=obj.data)
        else:
            return dict(type='data', data=obj)

    def getHostId(self) -> str:
        if self.host_id is None:
            return getOrCreateOption(None).hostId
        else:
            return self.host_id

    def getProxyManager(self) -> PlainProxyManager:
        return getOrCreateOption(self.host_id).plainProxyManager

    def getRunnableProxyManager(self) -> RunnableProxyManager:
        return getOrCreateOption(self.host_id).runnable_proxy_manager

    def reverseToArgObj(self, arg_obj: ArgObj[Any]) -> Any:
        if arg_obj['type'] == 'data':
            return arg_obj['data']
        else:
            result=dynamic_object()
            data: PlainProxy = arg_obj['data']

            if data['hostId'] == self.host_id:
                return self.getProxyManager().getById(data['id'])

            dynamic_object_ = self.getRunnableProxyManager().get(data['id'])
            if dynamic_object_ is not None:
                return dynamic_object_

            for _member in data['members']:
                key = _member['type']
                if key == 'property':
                    print('not implemented')
                elif key == 'function':
                    def closure():
                        member=_member
                        async def func(*args):
                            args_transformed = [self.args_auto_wrapper(arg) for arg in args]
                            args_transformed = [self.toArgObj(arg) for arg in args_transformed]
                            request: Request = {
                                'objectId': data['id'],
                                'id': getId(),
                                'meta':{},
                                'method': member['name'],
                                'args': args_transformed
                            }
                            res = await self.waitForRequest(request)
                            return res
                        return func
                    func=closure()
                    setattr(result, _member['name'], func)
                else:
                    raise ValueError('no such function')

            if(hasattr(result,'__call__')):
                async def call_func(*args):
                    return await result.__call__(*args)
                def __getitem__(key):
                    return result[key]
                call_func.__getitem__ = __getitem__
                result = call_func

            self.getRunnableProxyManager().set(data['id'], result)
            return result

    async def getObject(self, objectId: str) -> RunnableProxy:
        request: Request = {
            'id': getId(),
            'objectId': 'main0',
            'method': 'getMain',
            'args': [self.toArgObj(objectId)]
        }
        res = await self.waitForRequest(request)
        return res

    async def getMain(self) -> RunnableProxy:
        return await self.getObject('main')

message_receiver: Optional['MessageReceiver'] = None

def getMessageReceiver() -> 'MessageReceiver':
    global message_receiver
    if message_receiver is None:
        message_receiver = MessageReceiver()
    return message_receiver

RpcContext = Dict[str, Any]
NextFunction=Callable[[], None]
NextGenerator = Callable[[], NextFunction]
Interceptor = Callable[[RpcContext, Request, Client, NextFunction], None]
NextFunction = Callable[[], None]
AutoWrapper = Callable[[Any], Any]

shallowAutoWrapper: AutoWrapper = lambda obj: (
    asProxy(obj) if callable(obj) else
    asProxy(obj) if isinstance(obj, list) and any(callable(item) for item in obj) else
    asProxy(obj) if isinstance(obj, dict) and any(callable(value) for value in obj.values()) else
    obj
)
class symbol:
    def __init__(self,id_:str):
        self.id=id_
        pass
options: Dict[Union[str, symbol], 'MessageReceiverOptions'] = {}
default_host = symbol('defaultHost')

def getOrCreateOption(id_: Optional[Union[str, symbol]] = None) -> 'MessageReceiverOptions':
    if id_ is None:
        id_ = default_host
    if isinstance(id_, (str, symbol)):
        if id_ not in options:
            options[id_] = MessageReceiverOptions()
            options[id_].hostId=id_
        return options[id_]
    else:
        raise ValueError('Invalid argument passed')

RequestPendingDict = Dict[str, Dict[str, Callable[[Any], None]]]
from typing import Optional

class MessageReceiverOptions:
    def __init__(
        self,
    ):
        """
        初始化 MessageReceiverOptions 对象。
        """
        self.plainProxyManager = PlainProxyManager()
        self.runnable_proxy_manager = RunnableProxyManager()
        self.hostId = ''
        self.request_pending_dict = {}


class MessageReceiver:
    def __init__(self, host_id=None):
        self.rpc_server = None
        self.interceptors = []
        self.object_with_context = set()
        self.resultAutoWrapper = shallowAutoWrapper
        self.host_id = host_id
        self.getProxyManager().set(dict2obj({'getMain': lambda objectId: asProxy(self.getProxyManager().getById(objectId), self.getHostId())}), 'main0')

    def setResultAutoWrapper(self, auto_wrapper):
        self.resultAutoWrapper = auto_wrapper

    async def withContext(self, message, client, args, func):
        context = {}
        result = {}

        def generate_interceptor_executor(index_of_interceptor):
            if index_of_interceptor < len(self.interceptors):
                async def execute_this_interceptor():
                    
                    interceptor = self.interceptors[index_of_interceptor]
                    async def generateAndExecuteNext():
                        executor=generate_interceptor_executor(index_of_interceptor+1)
                        await executor()
                    v=await interceptor(context, message, client, generateAndExecuteNext)
                    if(hasattr(v, '__await__')):
                        v=await v
                return execute_this_interceptor
            else:
                async def execute_this_interceptor():
                    v=func(context, *args)
                    if(hasattr(v,'__await__')):
                        v=await v
                    result['value'] = v
                return execute_this_interceptor

        first_interceptor_executor = generate_interceptor_executor(0)
        await first_interceptor_executor()
        return result['value']

    def getProxyManager(self)->PlainProxyManager:
        return getOrCreateOption(self.host_id).plainProxyManager

    def getRunnableProxyManager(self)->RunnableProxyManager:
        return getOrCreateOption(self.host_id).runnable_proxy_manager

    def getHostId(self):
        return getOrCreateOption(self.host_id).hostId

    def getReqPending(self):
        return getOrCreateOption(self.host_id).request_pending_dict

    def setMain(self, obj):
        self.rpc_server = obj
        self.setObject('main', self.rpc_server, False)

    def setObject(self, id, obj, with_context):
        self.getProxyManager().set(obj, id)
        if with_context:
            self.object_with_context.add(id)

    def addInterceptor(self, interceptor):
        self.interceptors.append(interceptor)

    def putAwait(self, id, resolve, reject):
        self.getReqPending()[id] = {'resolve': resolve, 'reject': reject}

    async def onReceiveMessage(self,message:Union[Request,Response], client_for_call_back:Client):
        # print(f"{self.getHostId()} received a "
        #     f"{'reply, which is for ' + message['id'] + ' and it is ' + message['idFor'] if message['idFor'] else 'request, which id is ' + message['id']}")


        def isRequest(message:Union[Request,Response]):
            return message.get('idFor')==None

        # Is request, not reply
        if(isRequest(message)):
            args = [client_for_call_back.reverseToArgObj(x) for x in message['args']]

            try:
                object = self.getProxyManager().getById(message['objectId'])
                if object is None:
                    coroutine=client_for_call_back.sender.send(generateErrorReply(message, 'object not found', 100))
                    asyncio.ensure_future(coroutine)
                    return

                result = None
                should_with_context = message['objectId'] in self.object_with_context

                if message['method'] == '__call__':
                    if should_with_context:
                        result = await self.withContext(message, client_for_call_back, args, object)
                    else:
                        result = object(*args)
                else:
                    if should_with_context:
                        result = await self.withContext(message, client_for_call_back, args, getattr(object, message['method']))
                    else:
                        result = getattr(object, message['method'])(*args)

                result = self.resultAutoWrapper(result)
                wrapped_result = client_for_call_back.toArgObj(result)
                cor=client_for_call_back.sender.send({
                    'id': getId(),
                    'idFor': message['id'],
                    'data': wrapped_result,
                    'trace':None,
                    'status': 200
                })
                asyncio.ensure_future(cor)
            except Exception as e:
                trace_str = '\n'.join([x.strip() for x in str(e.__traceback__).split('\n')])
                client_for_call_back.sender.send({
                    'id': getId(),
                    'idFor': message['id'],
                    'data': dict(type='data',data=None),
                    'trace': trace_str,
                    'status': -1
                })
                import traceback
                traceback.print_exc()

        else:
            idFor=message.get('idFor')
            req_pending = self.getReqPending()
            if req_pending[idFor] is None:
                print(f"[{self.getHostId()}] no pending request for id {idFor}", message)
                return

            req = req_pending[idFor]
            del req_pending[idFor]
            if message['status'] == 200:
                req['resolve'](client_for_call_back.reverseToArgObj(message['data']))
            else:
                req['reject'](Exception(message))
idCOunt=0
def getId() -> str:
    global idCOunt
    idCOunt+=1
    return str(idCOunt)

# Example usage
if __name__ == "__main__":
    client = Client()
    try:
        main_proxy = asyncio.run(client.getMain())
        print(main_proxy)
    except Exception as e:
        import traceback
        traceback.print_exc()



