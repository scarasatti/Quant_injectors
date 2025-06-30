import asyncio
import json

sse_event_queues: dict[str, asyncio.Queue] = {}
sse_status: dict[str, bool] = {}

def register_user(user_id: str) -> asyncio.Queue:
    queue = asyncio.Queue()
    sse_event_queues[user_id] = queue
    sse_status.setdefault(user_id, False)  # default False se não existe
    return queue

def unregister_user(user_id: str):
    sse_event_queues.pop(user_id, None)
    sse_status.pop(user_id, None)

async def send_event(user_id: str, message) -> bool:
    queue = sse_event_queues.get(user_id)
    if queue:
        await queue.put(json.dumps(message))  # manda booleano ou string
        return True
    return False

def set_processing(user_id: str, value: bool):
    sse_status[user_id] = value

def is_processing(user_id: str) -> bool:
    return sse_status.get(user_id, False)
