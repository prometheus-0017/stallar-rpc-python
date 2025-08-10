# stallar-rpc-python

xuri-rpc is an RPC framework that superficially supports passing objects and callbacks. Of course, in reality, no objects are actually migrated; the actual computation still occurs where it originally resides.

Currently, only methods on objects can be passed; passing properties is not yet supported.

Supports both JavaScript and Python environments.

## Features

* Use a remote object as if it were a local object, without being limited to objects that need to be declared in advance.
* Since the object first returns to the local environment with its information before you proceed to call it, this largely avoids the helplessness of making an HTTP request only to receive a 404 error without knowing exactly which part went wrong. If you can't find it this time, at least you can see what options are available to you.

* Not restricted to a specific underlying communication method; you can use WebSocket, TCP, inter-process communication, integrate it into your existing services, or even polling-based HTTP.

  For dedicated WebSocket usage, we have implemented a WebSocket-based client.

  For other cases, you may need to: 1. Maintain a connection, 2. Implement a sender for the client. Connection maintenance is unrelated to this framework, except that you need to forward messages received on the connection to this framework. As for the sender, you won't need to do much.

## Use Cases

* Communication between browser workers

* Communication between iframes

* Communication between browser frontend and backend

## Installation

```
pip install stallar-rpc
```

## Examples

The examples below use WebSocket as the message carrier. Please install this component yourself; it will not be elaborated here.

### Using the RPC framework to execute a remote procedure and trigger a callback.

Server

```
import asyncio
import json
import websockets
from stallar_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
from stallar_rpc import setDebugFlag
setDebugFlag(True)
# Set hostName
setHostId('backend')

# Create a Sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        await self.ws.send(json.dumps(message))

# Set the main object that provides initial methods
from stallar_rpc import dict2obj
async def plus(a,b,callback):
    await callback(a + b)
    return a+b
getMessageReceiver().setMain(dict2obj({
    'plus': plus
}))

async def handle_connection(ws, path):
    # Create a client to send return messages
    client = Client()
    client.setSender(Sender(ws))

    try:
        async for data in ws:
            # Process received messages
            message = json.loads(data)
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(message, client))
    except Exception as error:
        print('Client connection error:', error)

start_server = websockets.serve(handle_connection, "", 18081)

try:
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except Exception as error:
    print('Server error:', error)
```

Client

```
import asyncio
import json
import websockets
from stallar_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
setHostId('backend')
from stallar_rpc import setDebugFlag
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

    ws = await websockets.connect('ws:#localhost:18081')

    async def on_message(data):
        await getMessageReceiver().onReceiveMessage(json.loads(data), client)
        print(f'Received server message: {data}')

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



Using multiple sets of RPC.

### Passing a context variable during invocation

First, the object you define should accept a dictionary representing the context as its first parameter.

Server

```
from stallar_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
from stallar_rpc import dict2obj
import websockets
import asyncio
import json

# Set hostName
setHostId('backend')

# Create a Sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        await self.ws.send(json.dumps(message))

# Set the main object that provides initial methods
getMessageReceiver().setMain(dict2obj({
}))
from stallar_rpc import dict2obj
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
    # Create a client to send return messages
    client = Client()
    client.setSender(Sender(websocket))

    async for data in websocket:
        try:
            # Process received messages
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(json.loads(data), client))
        except Exception as e:
            print('Client connection error:', e)

async def main():
    server = await websockets.serve(handle_connection, "localhost", 18081)
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
```

Client

```
import asyncio
import json
import websockets
from stallar_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId

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

    ws = await websockets.connect('ws:#localhost:18081')
    
    # Listen for messages
    async def listen():
        async for data in ws:
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(json.loads(data), client))
            print(f'Received server message: {data}')

    # Run listener and proceed
    asyncio.create_task(listen())

    client.setSender(Sender(ws))

    main_obj = await client.getObject('greeting')
    result = await main_obj.greeting()
    print(result)

asyncio.run(main())
```

## Tutorial

### Basic Information Transmission Process

An RPC call should include the following steps:

- A method of a remote object obtained from a certain client is invoked.
- The proxy of this remote object on the client side encapsulates a series of method calls into a request message.
- The client invokes its assigned ISender to send the message. At this point, the remote method call is asynchronously blocked here.
- The receiver on the receiving end receives the message and delegates it to the corresponding object for processing. When the receiver accepts a message, it should synchronously pass a client used for response.
- When the delegated object finishes processing, it returns the result.
- The result is sent back to the requesting side through the response client.
- After the receiver on the requesting side receives the message, the promise of this request is set to resolve or reject, completing this round of request.

### Classic Usage Flow

For complete code, please refer to the example.

**Server Side**

```python
# Set host ID
setHostId('backend')

# setMain & setObject accept an object as a parameter, not a dictionary. Be careful not to make a mistake.
from stallar_rpc import dict2obj

# Set the main object used to provide initial methods. You should add some methods to this object to return more remote objects, or you can directly implement some business logic calls within this main method.
async def plus(a, b, callback):
    await callback(a + b)
    return a + b

getMessageReceiver().setMain(dict2obj({
    'plus': plus
}))

# You have created a message channel through which you deserialize received information and pass it to MessageReceiver. When passing the received message to MessageReceiver, you also need to pass a client simultaneously, as you need something to send the return result of this call back.
async def handle_connection(ws, path):
    # Create a client for sending return messages
    client = Client()
    client.setSender(Sender(ws))

    try:
        async for data in ws:
            # Process received information
            message = json.loads(data)
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(message, client))
    except Exception as error:
        print('Client connection error:', error)

start_server = websockets.serve(handle_connection, "", 18081)
```

**Client Side**

```python
# Define a sender. Serialize a message object and send it out through some underlying transport mechanism, such as a process pipe or a websocket connection.
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        # message is an object that can be JSONified
        await self.ws.send(json.dumps(message))

# Set host ID
setHostId('frontend')
# Create a client; this client is an object that handles the complex operations of an RPC call.
client = Client()

# Create a channel. This channel is used both for sending messages and for receiving return results.
ws = await websockets.connect('ws://localhost:18081')

async def on_message(data):
    # Create a receiver; you need somewhere to receive the return results of what you send, right?
    await getMessageReceiver().onReceiveMessage(json.loads(data), client)
    print(f'Received server message: {data}')

# Run message reception in the background
async def listen():
    async for message in ws:
        asyncio.ensure_future(on_message(message))

# Start listening in the background
asyncio.ensure_future(listen())

# Bind the corresponding sender to the client
client.setSender(Sender(ws))

# Obtain the main object
main_proxy = await client.getMain()
# The main object is a remote object defined on the server side. You should obtain your defined functions from here. Call these functions to get further remote objects or execute some business logic.
def callback(result):
    # breakpoint()
    print('from callback', result)

result = await main_proxy.plus(1, 2, asProxy(callback))
```

### Host

This concept is equivalent to a logical host. Normally, it should correspond to your program. However, if your program may require multiple RPC connections, then each connection should correspond to such a logical host.

You should give your host a name, which should be unique within your entire distributed system. `setHostId` accepts a string parameter to specify the default host name. Typically, you should call this method only once.

For cases with multiple RPC connections, i.e., when you need to set up multiple hosts, you can pass a string parameter to the constructor of the client or receiver to specify the host to which this client or receiver belongs.

### asProxy, setArgsAutoWrapper

Parameters accepted by a remote object can be divided into data type and proxy type.

A data-type object is a completely data-representing object, such as a string, a dictionary, or other nested composite structures, which can be serialized in a definite way during the actual operation of the system.

A proxy-type object will be replicated to the remote end for processing. It is recommended that this object be immutable. Proxy-type objects should primarily carry computations and system logic structures in the system. These objects usually have extensive associations, making them unsuitable and unable to be serialized. During system execution, a proxy object will be generated and sent to the remote end. The remote host calls the proxy object to control the execution of the actual object's specific functions.

Although we provide a method to call remote objects, in principle, we do not recommend frequently creating and using remote objects because remote objects cannot be used as interchangeably with local objects. First, we do not provide a robust mechanism for unloading remote objects, i.e., there is no automatic garbage collection system. This could lead to some form of memory leak. Second, due to communication latency, calling remote methods may reduce program efficiency.

We provide an `asProxy` function to explicitly declare a parameter passed to a remote method as a proxy type. In implementation, it returns a representation object of a proxy-type object, which is an instance of `PreArgObj`.

We also provide a `setArgsAutoWrapper` function on the client. If in your system you can determine that parameters of a certain pattern are necessarily of proxy type, you can pass a function as a parameter to this function to achieve automatic conversion. Note that results returned by `asProxy` should be excluded.

### Context, Interceptor & setObject

We might face the following situation: For all requests, we may need to perform some preparations before the request is actually processed, such as creating a database session.

We call this mechanism "context." The context should be referenceable at any point during the entire request processing.

However, implementing this mechanism in asynchronous scenarios is relatively difficult, especially since browsers currently do not support a persistent global dictionary in an asynchronous environment.

As an alternative, we have added a mechanism where the function responsible for handling the request receives a dictionary representing the context as its first parameter. When building the server, add pre- and post-request processing mechanisms by calling the `addInterceptor` method, and use `await next()` to handle subsequent processing within them. Remote ends using this method only need to pass parameters normally, but when the server processes this request, the first parameter will be the context.

The specific process is as follows:

**Server Side**

```python
# Set an object on the server-side message receiver. Note that the first parameter of each method on this object is a context, and the third parameter of setObject is True, indicating that this is an object with the context mechanism enabled.
getMessageReceiver().setObject("greeting", dict2obj({
    "greeting": lambda context: f"hi, {context['a']} and {context['b']}"
}), True)

# Add an interceptor. Each interceptor is a method declared as follows. Parameters are context, current request message, return client, and next, which calls the next layer or the function body.
async def b(context, message, client, next):
    context['b'] = 'john'  # Context is a dictionary; you can add anything you want here.
    await next()  # Call the next layer

getMessageReceiver().addInterceptor(b)
```

**Client Side**

```python
# Obtain an object with context functionality via getObject.
main_obj = await client.getObject('greeting')
# When calling the function, there is no need to pass the context parameter.
result = await main_obj.greeting()
```

For complete code, see the example.