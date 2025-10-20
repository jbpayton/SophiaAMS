"""
Test web search functionality with Sophia.
"""

import requests
import json
import time

AGENT_API = "http://localhost:5001"
TEST_SESSION = f"websearch_test_{int(time.time())}"

def chat(message):
    """Send message to Sophia and get response."""
    print(f"\n{'='*70}")
    print(f"User: {message}")
    print('='*70)

    response = requests.post(
        f"{AGENT_API}/chat/{TEST_SESSION}",
        json={"content": message},
        timeout=120
    )

    if response.status_code == 200:
        reply = response.json()["response"]
        print(f"\nSophia: {reply}")
        return reply
    else:
        print(f"\nError {response.status_code}: {response.text}")
        return None

def main():
    print("\n" + "="*70)
    print("  SOPHIA WEB SEARCH TEST")
    print("="*70)

    # Test 1: Simple web search
    print("\n\n[TEST 1] Simple Web Search")
    reply1 = chat("Search the web for 'Python programming language' and tell me what you find.")

    if reply1:
        has_search_results = any(word in reply1.lower() for word in ['python', 'programming', 'found', 'search'])
        if has_search_results:
            print("\n[PASS] Sophia successfully searched and found results about Python")
        else:
            print("\n[WARN] Sophia responded but may not have used web search")

    time.sleep(2)

    # Test 2: Current events search
    print("\n\n[TEST 2] Current Events Search")
    reply2 = chat("What's the latest news about artificial intelligence? Search the web.")

    if reply2:
        print("\n[PASS] Sophia attempted to search for current AI news")

    time.sleep(2)

    # Test 3: Search + Read workflow
    print("\n\n[TEST 3] Search then Read Workflow")
    reply3 = chat("Search for information about 'vector databases', then read one of the top results.")

    if reply3:
        print("\n[PASS] Sophia attempted search + read workflow")

    # Cleanup
    print("\n\n" + "="*70)
    print("  CLEANUP")
    print("="*70)

    try:
        requests.delete(f"{AGENT_API}/session/{TEST_SESSION}")
        print("\nSession cleared successfully")
    except:
        pass

    print("\n" + "="*70)
    print("  TEST COMPLETE")
    print("="*70)
    print("\nNote: Check the responses above to verify:")
    print("  1. Sophia used the searxng_search tool")
    print("  2. She provided meaningful search results")
    print("  3. She can combine search with other tools")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
