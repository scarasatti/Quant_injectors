import asyncio

sse_event_queues: dict[str, asyncio.Queue] = {}

def register_user(user_id: str) -> asyncio.Queue:
    queue = asyncio.Queue()
    sse_event_queues[user_id] = queue
    return queue

def unregister_user(user_id: str):
    sse_event_queues.pop(user_id, None)

async def send_event(user_id: str, message: str):
    queue = sse_event_queues.get(user_id)
    if queue:
        await queue.put(message)
