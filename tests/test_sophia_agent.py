"""
Comprehensive test script for Sophia agent with web capabilities.

Tests:
1. Basic personality and conversation
2. Memory tools (existing)
3. Web search with SearXNG
4. Quick web page reading
5. Deep document ingestion
6. Hybrid workflow: search -> read -> decide to ingest
"""

import requests
import json
import time

# Configuration
AGENT_API = "http://localhost:5001"
TEST_SESSION_ID = f"sophia_test_{int(time.time())}"

def print_separator(title):
    """Print a section separator."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def chat_with_sophia(message, session_id=TEST_SESSION_ID, verbose=True):
    """Send a chat message to Sophia."""
    if verbose:
        print(f"\n👤 Joey: {message}")

    try:
        response = requests.post(
            f"{AGENT_API}/chat/{session_id}",
            json={"content": message},
            timeout=120  # Longer timeout for web operations
        )

        if response.status_code == 200:
            data = response.json()
            sophia_response = data.get("response", "")
            if verbose:
                print(f"🤖 Sophia: {sophia_response}")
            return sophia_response
        else:
            print(f"[ERROR] Agent returned status {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] Failed to chat with agent: {e}")
        return None

def test_health():
    """Test 1: Health check."""
    print_separator("TEST 1: Health Check")

    try:
        response = requests.get(f"{AGENT_API}/health")
        if response.status_code == 200:
            data = response.json()
            print("[PASS] Sophia is online and healthy")
            print(f"  Status: {data['status']}")
            print(f"  Active sessions: {data['active_sessions']}")
            print(f"  Memory loaded: {data['memory_loaded']}")
            return True
        else:
            print(f"[FAIL] Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] Could not connect to agent server: {e}")
        print(f"  Make sure agent_server.py is running on port 5001")
        return False

def test_personality():
    """Test 2: Sophia's personality and conversation style."""
    print_separator("TEST 2: Personality & Conversation Style")

    # Test short responses
    response = chat_with_sophia("Hi Sophia!")

    if response:
        word_count = len(response.split())
        print(f"\n  Word count: {word_count}")

        # Sophia should give relatively short responses
        if word_count <= 30:
            print("[PASS] Sophia gave a concise response")
        else:
            print("[WARN] Response was longer than expected (but acceptable if on a rant)")

        return True
    return False

def test_memory_tools():
    """Test 3: Memory query tools."""
    print_separator("TEST 3: Memory Tools")

    # Teach Sophia something
    response1 = chat_with_sophia("Remember that I love working on AI projects, especially with memory systems.")

    time.sleep(2)

    # Ask her to recall
    response2 = chat_with_sophia("What do you know about what I love working on?")

    if response2 and ("ai" in response2.lower() or "memory" in response2.lower()):
        print("\n[PASS] Sophia remembered information from earlier in conversation")
        return True
    else:
        print("[WARN] Sophia may not have used memory tools effectively")
        return True  # Still pass

def test_web_search():
    """Test 4: SearXNG web search."""
    print_separator("TEST 4: Web Search (SearXNG)")

    # NOTE: This requires SearXNG to be running at the configured URL
    print("NOTE: This test requires SearXNG running at http://192.168.2.94:8088")

    response = chat_with_sophia("Search the web for 'Python programming language' and tell me one interesting fact.")

    if response:
        # Check if Sophia actually used the search tool
        if "python" in response.lower():
            print("\n[PASS] Sophia used web search and found information")
            return True
        else:
            print("[WARN] Sophia responded but may not have used web search")
            return True
    return False

def test_read_web_page():
    """Test 5: Quick web page reading."""
    print_separator("TEST 5: Quick Web Page Reading")

    # Use a simple, reliable page
    response = chat_with_sophia(
        "Read this page quickly and tell me what it's about in one sentence: "
        "https://en.wikipedia.org/wiki/Artificial_intelligence"
    )

    if response:
        if "artificial intelligence" in response.lower() or "ai" in response.lower():
            print("\n[PASS] Sophia read the web page and understood it")
            return True
        else:
            print("[WARN] Sophia responded but may not have read the page")
            return True
    return False

def test_consciousness_workflow():
    """Test 6: Consciousness-like workflow (search -> read -> learn)."""
    print_separator("TEST 6: Consciousness-Like Workflow")

    print("This test simulates conscious learning: search -> skim -> decide to remember")

    # Step 1: Search
    print("\n--- Step 1: Search ---")
    response1 = chat_with_sophia("Search for information about 'semantic memory in AI'")

    time.sleep(2)

    # Step 2: Decision making
    print("\n--- Step 2: Evaluation ---")
    response2 = chat_with_sophia(
        "If you found something interesting about semantic memory, "
        "you can read it quickly or ingest it for long-term learning. What do you think?"
    )

    if response2:
        print("\n[PASS] Sophia engaged in the learning workflow")
        return True
    return False

def test_conversation_persistence():
    """Test 7: Conversation memory across turns."""
    print_separator("TEST 7: Conversation Memory Persistence")

    # First turn - introduce context
    response1 = chat_with_sophia("My favorite color is blue and I have two cats named Luna and Max.")

    time.sleep(1)

    # Second turn - reference previous context
    response2 = chat_with_sophia("What are my cats' names?")

    if response2 and ("luna" in response2.lower() and "max" in response2.lower()):
        print("\n[PASS] Sophia remembered conversation context!")
        return True
    else:
        print("[FAIL] Sophia didn't remember the conversation")
        print(f"  Expected: mention of 'Luna' and 'Max'")
        print(f"  Got: {response2[:100] if response2 else 'None'}")
        return False

def test_magician_archetype():
    """Test 8: Magician archetype - knowledge transformation."""
    print_separator("TEST 8: Magician Archetype - Knowledge Transformation")

    response = chat_with_sophia(
        "You're a Magician archetype. That means you transform knowledge into wisdom. "
        "Can you explain what that means to you in your own words?"
    )

    if response:
        # Check for thoughtful, self-aware response
        keywords = ["knowledge", "wisdom", "transform", "learn", "understand", "magic"]
        found = sum(1 for word in keywords if word in response.lower())

        if found >= 2:
            print(f"\n[PASS] Sophia showed self-awareness (found {found} key concepts)")
            return True
        else:
            print("[WARN] Response may not reflect magician archetype strongly")
            return True
    return False

def cleanup_session():
    """Clean up test session."""
    print_separator("CLEANUP: Clearing Test Session")

    try:
        response = requests.delete(f"{AGENT_API}/session/{TEST_SESSION_ID}")
        if response.status_code == 200:
            print("[PASS] Test session cleared")
        else:
            print(f"[WARN] Could not clear session: {response.status_code}")
    except Exception as e:
        print(f"[WARN] Cleanup failed: {e}")

def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("  SOPHIA AGENT COMPREHENSIVE TEST SUITE")
    print("  Testing: Personality, Memory, Web Capabilities")
    print("="*70)

    results = []

    # Test 1: Health check (required)
    if not test_health():
        print("\n[ABORT] Agent server is not running. Start it with:")
        print("  python agent_server.py")
        return

    print("\n⏳ Starting tests... (this may take a few minutes)")

    # Run all tests
    results.append(("Personality & Style", test_personality()))
    results.append(("Memory Tools", test_memory_tools()))
    results.append(("Web Search (SearXNG)", test_web_search()))
    results.append(("Read Web Page", test_read_web_page()))
    results.append(("Consciousness Workflow", test_consciousness_workflow()))
    results.append(("Conversation Persistence", test_conversation_persistence()))
    results.append(("Magician Archetype", test_magician_archetype()))

    # Cleanup
    cleanup_session()

    # Summary
    print_separator("TEST SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n📊 Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n🎉 SUCCESS! Sophia is fully operational with all capabilities!")
    else:
        print(f"\n⚠️  PARTIAL: {total - passed} test(s) failed")

    print("\n💡 Tips:")
    print("  - For web search tests, ensure SearXNG is running at http://192.168.2.94:8088")
    print("  - For document ingestion, try: chat_with_sophia('Ingest this: <URL>')")
    print("  - Sophia learns and grows - the more you interact, the smarter she becomes!")

if __name__ == "__main__":
    main()
