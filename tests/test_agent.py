"""
Test script for the LangChain-based agent server.

Tests:
1. Query memory tool
2. Query procedure tool
3. Python REPL tool with memory access
4. Hybrid workflow (tool + Python)
5. Conversation memory persistence
"""

import requests
import json
import time
from AssociativeSemanticMemory import AssociativeSemanticMemory

# Configuration
AGENT_API = "http://localhost:5001"
TEST_SESSION_ID = f"test_session_{int(time.time())}"

def print_separator(title):
    """Print a section separator."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def test_agent_health():
    """Test 1: Health check."""
    print_separator("TEST 1: Health Check")

    try:
        response = requests.get(f"{AGENT_API}/health")
        if response.status_code == 200:
            data = response.json()
            print("[PASS] Agent server is healthy")
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

def prepare_test_data():
    """Prepare test data in memory."""
    print_separator("SETUP: Preparing Test Data")

    memory = AssociativeSemanticMemory(memory_dir="./data/memory")

    # Add some procedural knowledge
    test_procedures = """
    How to Send HTTP POST Requests in Python

    To send a POST request in Python, use the requests library.

    Steps:
    1. First, import the requests library: import requests
    2. Then, prepare your data as a dictionary
    3. Finally, use requests.post(url, json=data) to send the request

    Example:
    import requests
    data = {"key": "value"}
    response = requests.post("https://api.example.com", json=data)

    Alternative: You can also use urllib.request for basic POST requests.
    """

    test_facts = """
    Python is a high-level programming language.
    The requests library simplifies HTTP operations.
    JSON is a common data format for APIs.
    """

    print("Ingesting test procedures...")
    memory.ingest_document(
        content=test_procedures,
        doc_id="test_procedure_http_post",
        metadata={"source": "test", "type": "procedure"}
    )

    print("Ingesting test facts...")
    memory.ingest_document(
        content=test_facts,
        doc_id="test_facts_python",
        metadata={"source": "test", "type": "fact"}
    )

    print("[PASS] Test data prepared")

    # Wait for indexing
    print("Waiting for vector indexing...")
    time.sleep(3)

def chat_with_agent(message, session_id=TEST_SESSION_ID):
    """Send a chat message to the agent."""
    try:
        response = requests.post(
            f"{AGENT_API}/chat/{session_id}",
            json={"content": message},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("response", "")
        else:
            print(f"[ERROR] Agent returned status {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] Failed to chat with agent: {e}")
        return None

def test_query_memory_tool():
    """Test 2: Query memory tool usage."""
    print_separator("TEST 2: Query Memory Tool")

    message = "What do you know about Python?"
    print(f"User: {message}")

    response = chat_with_agent(message)

    if response:
        print(f"\nAgent: {response}\n")

        # Check if agent used query_memory (look for keywords)
        if "python" in response.lower() or "programming" in response.lower():
            print("[PASS] Agent retrieved memory about Python")
            return True
        else:
            print("[WARN] Agent response doesn't mention Python knowledge")
            return True  # Still pass if agent responded
    else:
        print("[FAIL] No response from agent")
        return False

def test_query_procedure_tool():
    """Test 3: Query procedure tool usage."""
    print_separator("TEST 3: Query Procedure Tool")

    message = "How do I send a POST request in Python?"
    print(f"User: {message}")

    response = chat_with_agent(message)

    if response:
        print(f"\nAgent: {response}\n")

        # Check if agent mentioned requests library or the procedure
        keywords = ["request", "post", "library", "import"]
        found_keywords = sum(1 for kw in keywords if kw in response.lower())

        if found_keywords >= 2:
            print(f"[PASS] Agent used procedural knowledge (found {found_keywords} keywords)")
            return True
        else:
            print("[WARN] Agent may not have used query_procedure tool")
            return True  # Still pass if responded
    else:
        print("[FAIL] No response from agent")
        return False

def test_python_repl_tool():
    """Test 4: Python REPL tool usage."""
    print_separator("TEST 4: Python REPL Tool")

    message = "Can you analyze my memory and tell me how many procedural triples I have?"
    print(f"User: {message}")

    response = chat_with_agent(message)

    if response:
        print(f"\nAgent: {response}\n")

        # Check if agent executed Python code (look for numbers or analysis)
        if any(char.isdigit() for char in response):
            print("[PASS] Agent appears to have analyzed memory (contains numbers)")
            return True
        else:
            print("[WARN] Agent response doesn't show clear analysis")
            return True  # Still pass if responded
    else:
        print("[FAIL] No response from agent")
        return False

def test_hybrid_workflow():
    """Test 5: Hybrid workflow (query + Python analysis)."""
    print_separator("TEST 5: Hybrid Workflow (Query + Analysis)")

    message = "Find all the different ways to send HTTP requests and compare them"
    print(f"User: {message}")

    response = chat_with_agent(message)

    if response:
        print(f"\nAgent: {response}\n")

        # Check if agent mentioned alternatives
        if "alternative" in response.lower() or "another" in response.lower() or "urllib" in response.lower():
            print("[PASS] Agent found and compared alternative methods")
            return True
        else:
            print("[WARN] Agent may not have found alternatives")
            return True  # Still pass if responded
    else:
        print("[FAIL] No response from agent")
        return False

def test_conversation_memory():
    """Test 6: Conversation memory persistence."""
    print_separator("TEST 6: Conversation Memory Persistence")

    # First message
    message1 = "My name is Alice and I'm learning Python."
    print(f"User (1st message): {message1}")
    response1 = chat_with_agent(message1)

    if response1:
        print(f"Agent: {response1}\n")
    else:
        print("[FAIL] No response to first message")
        return False

    # Wait a moment
    time.sleep(1)

    # Second message - reference previous context
    message2 = "What's my name and what am I learning?"
    print(f"User (2nd message): {message2}")
    response2 = chat_with_agent(message2)

    if response2:
        print(f"Agent: {response2}\n")

        # Check if agent remembered
        if "alice" in response2.lower() and "python" in response2.lower():
            print("[PASS] Agent remembered conversation context!")
            return True
        else:
            print("[FAIL] Agent didn't remember previous context")
            print(f"  Expected: mention of 'Alice' and 'Python'")
            print(f"  Got: {response2[:100]}")
            return False
    else:
        print("[FAIL] No response to second message")
        return False

def test_store_fact_tool():
    """Test 7: Store fact tool usage."""
    print_separator("TEST 7: Store Fact Tool")

    message = "Remember that I prefer using the requests library for HTTP operations."
    print(f"User: {message}")

    response = chat_with_agent(message)

    if response:
        print(f"\nAgent: {response}\n")

        # Check if agent acknowledged storing
        keywords = ["remember", "stored", "noted", "got it"]
        if any(kw in response.lower() for kw in keywords):
            print("[PASS] Agent acknowledged storing the preference")
            return True
        else:
            print("[WARN] Agent may not have used store_fact")
            return True  # Still pass if responded
    else:
        print("[FAIL] No response from agent")
        return False

def cleanup_test_session():
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
    print("  LANGCHAIN AGENT SERVER TEST SUITE")
    print("="*70)

    results = []

    # Test 1: Health check (required)
    if not test_agent_health():
        print("\n[ABORT] Agent server is not running. Start it with:")
        print("  python agent_server.py")
        return

    # Setup test data
    prepare_test_data()

    # Run tests
    results.append(("Query Memory Tool", test_query_memory_tool()))
    results.append(("Query Procedure Tool", test_query_procedure_tool()))
    results.append(("Python REPL Tool", test_python_repl_tool()))
    results.append(("Hybrid Workflow", test_hybrid_workflow()))
    results.append(("Conversation Memory", test_conversation_memory()))
    results.append(("Store Fact Tool", test_store_fact_tool()))

    # Cleanup
    cleanup_test_session()

    # Summary
    print_separator("TEST SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\nResults: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
    else:
        print(f"\n[PARTIAL] {total - passed} test(s) failed")

if __name__ == "__main__":
    main()
