#!/usr/bin/env python3
"""
Demo startup script for SophiaAMS API and Streamlit client
"""
import subprocess
import sys
import time
import webbrowser
from threading import Thread

def start_api_server():
    """Start the FastAPI server"""
    print("🚀 Starting SophiaAMS API server...")
    subprocess.run([sys.executable, "api_server.py"])

def start_streamlit_client():
    """Start the Streamlit client"""
    print("🎨 Starting Streamlit test client...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "streamlit_client.py"])

def main():
    print("🧠 SophiaAMS Demo Startup")
    print("=" * 40)

    choice = input("""
Choose what to start:
1. API Server only (port 8000)
2. Streamlit Client only (port 8501)
3. Both (recommended)
4. Exit

Enter choice (1-4): """).strip()

    if choice == "1":
        start_api_server()
    elif choice == "2":
        print("⚠️  Make sure API server is running on localhost:8000 first!")
        input("Press Enter to continue...")
        start_streamlit_client()
    elif choice == "3":
        print("🎯 Starting both API server and Streamlit client...")
        print("📝 API will be on: http://localhost:8000")
        print("🎨 Streamlit will be on: http://localhost:8501")
        print("")

        # Start API server in background thread
        api_thread = Thread(target=start_api_server, daemon=True)
        api_thread.start()

        # Wait a moment for API server to start
        print("⏳ Waiting for API server to start...")
        time.sleep(3)

        # Start Streamlit client
        start_streamlit_client()
    else:
        print("👋 Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()