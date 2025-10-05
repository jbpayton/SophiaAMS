#!/usr/bin/env python3
"""
SophiaAMS Quick Start Script
Launches the complete memory system with API server and interactive client
"""

import subprocess
import sys
import time
import os
from pathlib import Path

def check_requirements():
    """Check if basic requirements are met"""
    print("🔍 Checking requirements...")

    # Check if we're in the right directory
    if not Path("api_server.py").exists() or not Path("streamlit_client.py").exists():
        print("❌ Error: Required files not found. Please run this script from the SophiaAMS directory.")
        return False

    # Check if .env file exists and warn if not
    if not Path(".env").exists():
        print("⚠️  Warning: .env file not found.")
        print("   Create a .env file with your LLM configuration:")
        print("   LLM_API_BASE=http://your-llm-server:1234/v1")
        print("   LLM_API_KEY=your-api-key")
        print("   EXTRACTION_MODEL=your-model-name")
        print()

        choice = input("Continue anyway? (y/N): ").strip().lower()
        if choice != 'y':
            return False

    print("✅ Requirements check passed!")
    return True

def main():
    print("🧠 SophiaAMS - Associative Semantic Memory System")
    print("=" * 55)
    print("An intelligent memory system for LLM-based applications")
    print()

    if not check_requirements():
        sys.exit(1)

    print("🚀 Starting SophiaAMS components...")
    processes = []

    try:
        # Start API server
        print("🔧 Starting API server (FastAPI)...")
        api_process = subprocess.Popen(
            [sys.executable, "api_server.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        processes.append(("API Server", api_process))

        # Wait for API server to start
        print("   ⏳ Waiting for API server to initialize...")
        time.sleep(4)

        # Start Streamlit client
        print("💻 Starting interactive client (Streamlit)...")
        streamlit_process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "streamlit_client.py",
             "--browser.gatherUsageStats=false"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        processes.append(("Streamlit Client", streamlit_process))

        # Wait for Streamlit to start
        print("   ⏳ Waiting for Streamlit to initialize...")
        time.sleep(4)

        print("\n" + "="*55)
        print("✅ SophiaAMS is now running!")
        print("="*55)
        print("🎯 Main Interface:      http://localhost:8501")
        print("🌐 API Server:          http://localhost:8000")
        print("📚 API Documentation:   http://localhost:8000/docs")
        print("💊 Health Check:        http://localhost:8000/health")
        print()
        print("🎨 Features Available:")
        print("   • Interactive chat with memory-aware responses")
        print("   • Document upload and processing")
        print("   • Memory exploration and visualization")
        print("   • Real-time conversation buffering")
        print("   • Semantic knowledge graph browsing")
        print()
        print("💡 Tips:")
        print("   • Try asking about topics you've discussed before")
        print("   • Upload text files to expand the knowledge base")
        print("   • Explore the 'Memory Query' tab to search your knowledge")
        print("   • Check 'Auto Memory' to see retrieval in action")
        print()
        print("⚠️  Press Ctrl+C to stop all services")
        print("="*55)

        # Keep running until interrupted
        while True:
            # Check if any process has died
            for name, process in processes:
                if process.poll() is not None:
                    print(f"\n❌ {name} has stopped unexpectedly!")
                    return
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down SophiaAMS...")

    except Exception as e:
        print(f"\n❌ Error starting SophiaAMS: {e}")

    finally:
        # Clean up processes
        print("🧹 Cleaning up processes...")
        for name, process in processes:
            try:
                if process.poll() is None:  # Process is still running
                    print(f"   Stopping {name}...")
                    process.terminate()
                    # Give it a moment to terminate gracefully
                    time.sleep(1)
                    if process.poll() is None:  # Still running, force kill
                        process.kill()
            except Exception as e:
                print(f"   Error stopping {name}: {e}")

        print("✅ All services stopped.")
        print("💭 Your conversations and knowledge remain stored for next time!")
        print("🙏 Thanks for using SophiaAMS!")

if __name__ == "__main__":
    main()