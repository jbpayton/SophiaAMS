"""
Quick interactive test for Sophia agent.

This script provides a simple way to chat with Sophia and test her capabilities.
"""

import requests
import sys
import time

AGENT_API = "http://localhost:5001"
SESSION_ID = f"quick_test_{int(time.time())}"

def check_health():
    """Check if agent is running."""
    try:
        response = requests.get(f"{AGENT_API}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def chat(message):
    """Send a message to Sophia."""
    try:
        response = requests.post(
            f"{AGENT_API}/chat/{SESSION_ID}",
            json={"content": message},
            timeout=120
        )

        if response.status_code == 200:
            return response.json()["response"]
        else:
            return f"Error: Status {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    print("="*70)
    print("  SOPHIA QUICK TEST")
    print("="*70)

    # Check if agent is running
    print("\n🔍 Checking if Sophia is online...")
    if not check_health():
        print("❌ Sophia is not running!")
        print("\nStart the agent with: python agent_server.py")
        return

    print("✅ Sophia is online!\n")

    # Test personality
    print("="*70)
    print("TEST 1: Basic Conversation")
    print("="*70)

    print("\n👤 You: Hi Sophia!")
    response = chat("Hi Sophia!")
    print(f"🤖 Sophia: {response}\n")

    # Test memory
    print("="*70)
    print("TEST 2: Teaching Sophia")
    print("="*70)

    print("\n👤 You: Remember that my favorite programming language is Python.")
    response = chat("Remember that my favorite programming language is Python.")
    print(f"🤖 Sophia: {response}\n")

    time.sleep(1)

    print("👤 You: What's my favorite programming language?")
    response = chat("What's my favorite programming language?")
    print(f"🤖 Sophia: {response}\n")

    # Test tool awareness
    print("="*70)
    print("TEST 3: Tool Awareness")
    print("="*70)

    print("\n👤 You: What tools do you have available?")
    response = chat("What tools do you have available?")
    print(f"🤖 Sophia: {response}\n")

    # Interactive mode option
    print("="*70)
    print("\n✅ Quick tests complete!")
    print("\nWould you like to enter interactive mode? (y/n)")

    choice = input("> ").strip().lower()

    if choice == 'y':
        print("\n" + "="*70)
        print("  INTERACTIVE MODE")
        print("  Type 'quit' or 'exit' to end conversation")
        print("="*70 + "\n")

        while True:
            user_input = input("👤 You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("🤖 Sophia: Goodbye! 👋")
                break

            if not user_input:
                continue

            response = chat(user_input)
            print(f"🤖 Sophia: {response}\n")

    print("\n" + "="*70)
    print("  Test session complete!")
    print("="*70)

    # Cleanup
    try:
        requests.delete(f"{AGENT_API}/session/{SESSION_ID}")
        print("\n✨ Session cleaned up")
    except:
        pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
        sys.exit(0)
