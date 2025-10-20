"""
Test script for streaming callback handler
"""
import asyncio
import sys
from agent_server import StreamingCallbackHandler

async def test_callback():
    """Test the callback handler."""
    callback = StreamingCallbackHandler()

    # Simulate some events
    await callback.send_event("thinking", {"status": "Starting..."})
    await callback.send_event("tool_start", {
        "tool": "query_memory",
        "input": "test query"
    })
    await callback.send_event("tool_end", {
        "tool": "query_memory",
        "output": "Test result"
    })
    await callback.send_event("final_response", {
        "response": "Here is the answer"
    })

    # Signal completion
    await callback.events.put(None)

    # Read and print all events
    print("Events received:")
    while True:
        event = await callback.events.get()
        if event is None:
            break
        print(f"  {event['type']}: {event['data']}")

    print("\nCallback test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_callback())
