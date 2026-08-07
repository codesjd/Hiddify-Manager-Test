import asyncio

import sonora.aio

from . import test_pb2_grpc
from .test_pb2 import HelloRequest


async def temp():
    async with sonora.aio.insecure_web_channel(f"http://localhost:9000") as channel:
        stub = test_pb2_grpc.HelloStub(channel)
        print(await stub.SayHello(HelloRequest(req="F")))


asyncio.run(temp())
