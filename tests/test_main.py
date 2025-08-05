from stallar_rpc import  Message,MessageReceiverOptions,RunnableProxyManager,PlainProxyManager,setHostId,Client,ISender,asProxy,getMessageReceiver,MessageReceiver 
from typing import Any
class DirectSender(ISender):
    def __init__(self, client_callback:Client, msg_receiver_to:MessageReceiver):
        self.client_callback = client_callback
        self.msg_receiver = msg_receiver_to

    async def send(self, message:Message):
        await self.msg_receiver.onReceiveMessage(message, self.client_callback)
        print('send', message)
from stallar_rpc import dict2obj
async def main():
    setHostId('frontJs')
    
    host_id = 'backendJs'
    
    message_receiver_backend = MessageReceiver(host_id)
    
    object_test = dict2obj({
        'say': lambda name: print('hello ', name)
    })
    class TestFunc:
        def hello(self,a,b,result):
            result(a+b)
            return a+b
        def getObject(self):
            return asProxy(object_test,host_id)
    
    message_receiver_backend.setMain(TestFunc())
    
    message_receiver_backend.setResultAutoWrapper(lambda x: x)

    client = Client()
    client_on_backend = Client(host_id)
    sender = DirectSender(client_on_backend, message_receiver_backend)
    back_sender = DirectSender(client, getMessageReceiver())
    client.sender = sender
    client_on_backend.sender = back_sender
    client.setArgsAutoWrapper(lambda x: x)
    
    rpc = await client.getMain()
    try:
        callback = lambda a: expect(a==3) 
        result = await rpc.hello(1, 2, asProxy(callback))
        expect(result==3) 
    except Exception as e:
        print(e)
    
    remote_object = await rpc.getObject()
    await remote_object.say('world')


# Test case
# import unittest
def expect(a):
    assert a 

# class TestFunca(unittest.TestCase):
#     async def test_should_return_correct_string(self):
#         await main()

# unittest.main()
import asyncio
def test_main():
    if __name__ == "__main__":
        try:
            main_proxy = asyncio.run(main())
            print(main_proxy)
        except Exception as e:
            import traceback
            traceback.print_exc()



