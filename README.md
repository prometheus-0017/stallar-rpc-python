# xuri-rpc-python
xuri-rpc是一款在表面上支持了传递对象和回调的RPC框架。当然，实际上。并没有对象发生迁移，实际的计算还发生在它本来的位置。

目前只支持传递对象上的方法，暂不支持传递属性。

支持JavaScript和Python两种环境。

## 特点

* 像使用一个本地对象一样去使用一个远程对象。并且不局限于需要事先声明的对象。
* 因为对象首先会带着他的信息返回到本地来，你才会接着调用。这就在很大程度上避免了你调一个HTTP的请求，然后给你报404，你却找不着到底是哪个地方没对上的一种无力感。如果这一次再找不着你至少可以看到你还有什么可以选的。

* 不限制底层通信方式，你可以使用websocket，TCP，进程通信，合并到你现有的服务中，甚至基于轮询的http。

  对于专用一个websocket的情况，我们实现了基于websocket的client

  其它情况你可能需要：1，维护一个连接，2，实现一个用于client的sender，连接的维护和本框架无关，除了你需要将连接上收到的信息转发给本框架，而对于sender，你不会做太多事情

## 使用场景

* 浏览器workers之间通信

* iframes之间通信

* 浏览器前端和后端通信

## 安装

```
pip install xuri-rpc
```

## 示例

示例中使用了web socket作为信息载体。这个部分自己装这里不再赘述。

### 使用RPC框架进行一个远程的过程执行并触发一次回调。

服务端

```
import asyncio
import json
import websockets
from xuri_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
from xuri_rpc import setDebugFlag
setDebugFlag(True)
# 设置hostName
setHostId('backend')

# 创建一个Sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        await self.ws.send(json.dumps(message))

# 设置用于提供起始方法的main对象
from xuri_rpc import dict2obj
async def plus(a,b,callback):
    await callback(a + b)
    return a+b
getMessageReceiver().setMain(dict2obj({
    'plus': plus
}))

async def handle_connection(ws, path):
    # 创建一个client用于发送返回信息
    client = Client()
    client.setSender(Sender(ws))

    try:
        async for data in ws:
            # 处理接收到的信息
            message = json.loads(data)
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(message, client))
    except Exception as error:
        print('客户端连接错误:', error)

start_server = websockets.serve(handle_connection, "", 18081)

try:
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except Exception as error:
    print('服务器错误:', error)
```

客户端

```
import asyncio
import json
import websockets
from xuri_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
setHostId('backend')
from xuri_rpc import setDebugFlag
setDebugFlag(True)


# define a sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        # message is an object can be jsonified
        await self.ws.send(json.dumps(message))

async def main():
    setHostId('frontend')
    client = Client()

    ws = await websockets.connect('ws://localhost:18081')

    async def on_message(data):
        await getMessageReceiver().onReceiveMessage(json.loads(data), client)
        print(f'收到服务器消息: {data}')

    # Run message reception in the background
    async def listen():
        async for message in ws:
            asyncio.ensure_future(on_message(message))

    # Start listening in the background
    asyncio.ensure_future(listen())

    client.setSender(Sender(ws))

    main_proxy = await client.getMain()
    def callback(result):
        # breakpoint()
        print('from callback', result)
    result = await main_proxy.plus(1, 2, asProxy(callback))
    print('from rpc', result)

asyncio.run(main())
```



使用多组 RPC。

### 在调用的时候传递一个上下文变量

首先你定义的对象接收的第一个参数应当是一个表示上下文的字典。

服务端

```
from xuri_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
from xuri_rpc import dict2obj
import websockets
import asyncio
import json

# 设置hostName
setHostId('backend')

# 创建一个Sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        await self.ws.send(json.dumps(message))

# 设置用于提供起始方法的main对象
getMessageReceiver().setMain(dict2obj({
}))
from xuri_rpc import dict2obj
getMessageReceiver().setObject("greeting",dict2obj( {
    "greeting": lambda context: f"hi,{context['a']} and {context['b']}"
}), True)
async def a(context,message,client,next):
    context['a']='mike'
    await next()
async def b(context,message,client,next):
    context['b']='john'
    await next()

getMessageReceiver().addInterceptor(a)
getMessageReceiver().addInterceptor(b)

async def handle_connection(websocket, path):
    # 创建一个client用于发送返回信息
    client = Client()
    client.setSender(Sender(websocket))

    async for data in websocket:
        try:
            # 处理接收到的信息
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(json.loads(data), client))
        except Exception as e:
            print('客户端连接错误:', e)

async def main():
    server = await websockets.serve(handle_connection, "localhost", 18081)
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
```

客户端

```
import asyncio
import json
import websockets
from xuri_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId

# define a sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        # message is an object can be jsonified
        await self.ws.send(json.dumps(message))

async def main():
    setHostId('frontend')
    client = Client()

    ws = await websockets.connect('ws://localhost:18081')
    
    # Listen for messages
    async def listen():
        async for data in ws:
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(json.loads(data), client))
            print(f'收到服务器消息: {data}')

    # Run listener and proceed
    asyncio.create_task(listen())

    client.setSender(Sender(ws))

    main_obj = await client.getObject('greeting')
    result = await main_obj.greeting()
    print(result)

asyncio.run(main())
```

## 教程

### 基本的信息发送流程

一次RPC调用应当包括以下过程:

- 一个从某个client当中获得的远程对象的一个方法被调用。
- 这个远程对象的代理调用client封装一系列的方法最后组成一条请求(Response)信息(Message)
-  Client调用分配给其的ISender。发送消息。此远程方法通过异步的方式阻塞在这里。
- 接收端的receiver收到信息以后，委派给对应的对象进行处理。在receiver接受一个消息的时候，应当同步传递一个用于应答的client。
- 当委派对象处理完时返回结果。
- 返回结果通过应答client返回给请求侧。
- 请求侧的receiver收到消息后。此请求的promise被设置为resolve或reject完成本轮请求。

### 经典的使用流程

完整代码参见示例。

服务端

```

# 设置host Id
setHostId('backend')

#setMain&setObject接受一个对象作为参数而非字典。注意不要弄错了。
from xuri_rpc import dict2obj

#设置用于提供起始方法的main对象,在这个面对象里，你应当添加一些方法返回更多的远程对象。或者你也可以直接就在这个main方法里实现一些业务逻辑的调用。
async def plus(a,b,callback):
    await callback(a + b)
    return a+b
getMessageReceiver().setMain(dict2obj({
    'plus': plus
}))

#你创建了某种方式的消息通道从中获得信息反序列化之后传递给 MessageReceiver,当你把收到的消息传递给MessageReceiver的时候，你还需要同时传递一个client，毕竟这次调用的返回结果你得找个东西发回去。
async def handle_connection(ws, path):
    # 创建一个client用于发送返回信息
    client = Client()
    client.setSender(Sender(ws))

    try:
        async for data in ws:
            # 处理接收到的信息
            message = json.loads(data)
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(message, client))
    except Exception as error:
        print('客户端连接错误:', error)

start_server = websockets.serve(handle_connection, "", 18081)
```

客户端

```

#定义一个发送装置。把一个消息对象序列化，并通过某一种底层的传输机制发送出去,比如说一个进程管道，或者是一个web socket连接。
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        # message is an object can be jsonified
        await self.ws.send(json.dumps(message))

#设置host ID。
setHostId('frontend')
#创建一个client，这个client是完成了RPC调用的一些复杂操作的对象。
client = Client()


#创建一个管道。这个管道。既被用于发送信息，也被用于接收返回结果。
ws = await websockets.connect('ws://localhost:18081')

async def on_message(data):
    #创建一个receiver,你发出去的东西总得找个地方接返回结果，是吧？
    await getMessageReceiver().onReceiveMessage(json.loads(data), client)
    print(f'收到服务器消息: {data}')

# Run message reception in the background
async def listen():
    async for message in ws:
        asyncio.ensure_future(on_message(message))

# Start listening in the background
asyncio.ensure_future(listen())

#给client绑定对应的sender
client.setSender(Sender(ws))



#获得main对象
main_proxy = await client.getMain()
#main对象是服务侧定义的一个远程对象，你应当从这里获得到你定义的函数。调用这些函数，获得更进一步的远程对象或者执行一些业务逻辑。
def callback(result):
    # breakpoint()
    print('from callback', result)
result = await main_proxy.plus(1, 2, asProxy(callback))

```



### host

这个东西相当于一个逻辑上的主机概念。正常情况下，它应当是对应于你这个程序的。但是如果你的程序里可能需要很多种rpc连接，那么每一种连接应当对应于一个这样的逻辑主机一个host。

你应当给你的主机起一个名字这个名字在你的一整套。 分布式。系统里应当是唯一的。 setHostId接受一个字符串作为参数指定默认的主机的名称。通常情况下，你应当且仅应当调用一次这个方法。

对于有多个rpc连接的情况，也就是你需要设置多个host的情况。你可以在client和receiver的构造函数中传入一个字符串参数作为这个client或者receiver的所属host。

### asProxy，setArgsAutoWrapper

一个远程对象接受的参数对象可以分为data类型和proxy类型。 

Data类型的对象就是一个完全表示数据的对象,例如一个字符串或一个字典或者其它嵌套，复合结构,它可以被以一种确定的方式序列化。在系统实际运行的过程当中。

Proxy类型对象将会被复制到远程端被远程端处理。推荐这个对象是不可变的对象。而proxy类型的对象。应当是在系统中主要负责承载计算的承载系统逻辑的部分结构。通常这类对象具有广泛的关联,不适合也不能被序列化。在系统执行的过程当中，此对象将会产生一个代理对象发送到远程上。远程主机调用代理对象来控制对象本体执行具体函数。

虽然我们提供了一种调用远程对象的方法，但是,原则上我们不建议频繁的创建和使用远程对象,因为不可能把远程对象和本地对象当成一种东西来用。首先我们并没有提供一个健全的卸载远程对象的机制,即没有一种自动的垃圾回收系统。因此，这可能会导致某种意义上的内存泄露。其次是受通信延迟的影响,调用远程方法可能会降低程序效率。

我们提供了一个asProxy函数。显式地声明一个传递给远程方法的参数是proxy类型。在实现上，它返回了一个proxy类型对象的表示对象,这是一个PreArgObj的实例。

我们还在client上提供了一个setArgsAutoWrapper函数。如果在你的系统中，你能够确定某一种模式的参数必然是一个proxy类型的参数，那么你可以通过给这个函数传递一个函数作为参数。来实现一种自动的转换。注意，应当放过as proxy返回的结果。

### context,interceptor & setObject

我们可能需要面临这样的一个情况:对于所有的请求，在请求被实际处理之前，我们可能需要进行一些准备,例如创建一个数据库会话。

我们将这种机制称之为上下文。上下文应当能够在请求处理的全过程当中的任意一个地方都可以被引用。

但是这个机制在异步情况下实现起来比较困难，尤其是浏览器端目前不支持在asynchronized的环境下的一个持续的全局的字典。

作为一个替代方法。我们增加了一种机制。在这个机制中。负责处理请求的函数接受到的第一个参数为一个表示上下文的字典。在构建服务器的时候。通过调用addInterceptor 方法。增加请求前后的处理机制。并在其中await的调用next处理后续。使用这个方法的远程端只需要正常的传递参数。但是在服务端处理这个请求的时候会增加第一个参数为context。

具体流程为：

服务端

```
#在服务端的message server上设置一个Object。注意这个object上的每一个方法的第一个参数都是一个context。且set object的第三个参数为true,表示。这是一个启用了context的机制的对象。。
getMessageReceiver().setObject("greeting",dict2obj( {
    "greeting": lambda context: f"hi,{context['a']} and {context['b']}"
}), True)
#添加拦截器。每个拦截器是如下声明的一个方法。参数依次是上下文。当前请求的message。返回的client。调用下一层。拦截器或者是函数本体的next。
async def b(context,message,client,next):
    context['b']='john'# Context是一个字典，你可以在这里添加上任何你想要做的事情。
    await next()#调用下一层

getMessageReceiver().addInterceptor(b)
```

客户端

```
#通过 getObject 的获得具有上下文功能的对象。
main_obj = await client.getObject('greeting')
#调用函数的时候，不需要传递上下文这个参数。
result = await main_obj.greeting()
```

完整代码见示例
