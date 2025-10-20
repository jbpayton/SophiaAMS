"""
Test script for automatic memory recall
"""
import requests
import json

API_URL = "http://localhost:5001"
SESSION_ID = "test_auto_recall"

def test_query(query: str):
    """Test a query against the agent."""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    response = requests.post(
        f"{API_URL}/chat/{SESSION_ID}/stream",
        json={"content": query},
        headers={"Content-Type": "application/json"},
        stream=True
    )

    print("\nAgent Response:")
    print('-'*60)

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                try:
                    event = json.loads(line[6:])

                    if event['type'] == 'final_response':
                        print(event['data']['response'])
                        print('-'*60)
                    elif event['type'] == 'tool_start':
                        print(f"\n🔧 Using tool: {event['data']['tool']}")
                        if 'log' in event['data']:
                            # Extract reasoning
                            log_lines = event['data']['log'].split('\n')
                            for log_line in log_lines:
                                if log_line.strip() and not log_line.strip().startswith('Action'):
                                    print(f"  💭 {log_line.strip()}")
                    elif event['type'] == 'tool_end':
                        result = event['data']['output'][:100]
                        print(f"  ✅ Result: {result}...")

                except json.JSONDecodeError:
                    pass

if __name__ == "__main__":
    print("Testing Automatic Memory Recall")
    print("================================\n")
    print("This test will check if the agent automatically recalls memories about Kasane Teto")
    print("without needing to explicitly call query_memory.\n")

    # Test 1: Simple question about Teto
    test_query("Who is Kasane Teto?")

    # Test 2: More specific question
    test_query("What are some of Teto's top songs?")

    # Test 3: Related query
    test_query("Tell me about teto")

    print("\n" + "="*60)
    print("Test complete!")
    print("="*60)
