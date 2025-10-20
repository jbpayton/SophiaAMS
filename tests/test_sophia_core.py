"""
Core functionality tests for Sophia agent.
Tests basic capabilities without requiring spacy/document ingestion.
"""

import requests
import json
import time

AGENT_API = "http://localhost:5001"
TEST_SESSION = f"test_{int(time.time())}"

def test(name):
    """Decorator to print test names."""
    def decorator(func):
        def wrapper():
            print(f"\n{'='*70}")
            print(f"TEST: {name}")
            print('='*70)
            try:
                result = func()
                status = "[PASS]" if result else "[FAIL]"
                print(f"\n{status}: {name}")
                return result
            except Exception as e:
                print(f"\n[ERROR]: {name}")
                print(f"   {str(e)}")
                return False
        return wrapper
    return decorator

def chat(message, session=TEST_SESSION):
    """Send message to Sophia."""
    print(f"\nUser: {message}")

    response = requests.post(
        f"{AGENT_API}/chat/{session}",
        json={"content": message},
        timeout=60
    )

    if response.status_code == 200:
        reply = response.json()["response"]
        print(f"Sophia: {reply}")
        return reply
    else:
        print(f"Error: {response.status_code}")
        return None

@test("Server Health Check")
def test_health():
    """Verify server is running."""
    response = requests.get(f"{AGENT_API}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"   Status: {data['status']}")
        print(f"   Memory loaded: {data['memory_loaded']}")
        return data['status'] == 'healthy' and data['memory_loaded']
    return False

@test("Sophia Personality - Short Responses")
def test_personality():
    """Test if Sophia gives appropriately short responses."""
    reply = chat("Hi Sophia!")
    if reply:
        words = len(reply.split())
        print(f"   Response length: {words} words")
        # Allow up to 40 words (she might rant a bit on first greeting)
        return words <= 40
    return False

@test("Memory - Store Fact")
def test_store_fact():
    """Test storing a fact in memory."""
    reply = chat("Remember that I love Python programming.")
    if reply:
        # Should acknowledge storing
        return any(word in reply.lower() for word in ['remember', 'stored', 'noted', 'got'])
    return False

@test("Conversation Memory - Short Term")
def test_conversation_memory():
    """Test if Sophia remembers within the same conversation."""
    # First, tell her something
    chat("My favorite color is purple.")
    time.sleep(1)

    # Then ask her to recall
    reply = chat("What's my favorite color?")
    if reply:
        return 'purple' in reply.lower()
    return False

@test("Web Reading - Quick Fetch")
def test_web_reading():
    """Test reading a web page."""
    reply = chat("Read this page and tell me what it's about in one sentence: https://en.wikipedia.org/wiki/Artificial_intelligence")
    if reply:
        # Should mention AI or artificial intelligence
        return 'artificial' in reply.lower() or 'ai' in reply.lower() or 'intelligence' in reply.lower()
    return False

@test("Tool Awareness")
def test_tool_awareness():
    """Test if Sophia knows what tools she has."""
    reply = chat("What tools can you use?")
    if reply:
        # Should mention at least a few tools
        tools_mentioned = sum([
            'memory' in reply.lower(),
            'search' in reply.lower(),
            'read' in reply.lower(),
            'python' in reply.lower()
        ])
        print(f"   Tools mentioned: {tools_mentioned}/4")
        return tools_mentioned >= 2
    return False

@test("Magician Archetype")
def test_archetype():
    """Test if Sophia understands her archetype."""
    reply = chat("What's your Jungian archetype?")
    if reply:
        return 'magician' in reply.lower()
    return False

@test("Session Cleanup")
def test_cleanup():
    """Test session cleanup."""
    response = requests.delete(f"{AGENT_API}/session/{TEST_SESSION}")
    return response.status_code == 200

def main():
    print("\n" + "="*70)
    print("  SOPHIA CORE FUNCTIONALITY TEST SUITE")
    print("="*70)

    tests = [
        test_health,
        test_personality,
        test_store_fact,
        test_conversation_memory,
        test_web_reading,
        test_tool_awareness,
        test_archetype,
        test_cleanup
    ]

    results = [t() for t in tests]

    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70)

    passed = sum(results)
    total = len(results)

    print(f"\nResults: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED! Sophia is fully operational!")
    elif passed >= total * 0.75:
        print(f"\n[MOSTLY OK] MOSTLY WORKING: {total - passed} test(s) failed")
    else:
        print(f"\n[WARNING] ISSUES DETECTED: {total - passed} test(s) failed")

    print("\n" + "="*70)

    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        exit(1)
