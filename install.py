#!/usr/bin/env python3
"""
Install script for SophiaAMS
This script will:
1. Install all Python dependencies from requirements.txt
2. Download and install the spaCy English language model
"""

import subprocess
import sys
import os

def print_section(title):
    """Print a section title in a nice format."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

def run_command(command, description):
    """Run a command and print its output."""
    print(f"Running: {description}...")
    try:
        process = subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"Success: {description}")
        if process.stdout.strip():
            print("Output:")
            print(process.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {description} failed!")
        print(f"Command: {' '.join(command)}")
        print(f"Exit code: {e.returncode}")
        if e.stdout:
            print("Output:")
            print(e.stdout)
        if e.stderr:
            print("Error:")
            print(e.stderr)
        return False

def install_dependencies():
    """Install all dependencies from requirements.txt."""
    print_section("Installing Python Dependencies")
    return run_command(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        "Installing dependencies from requirements.txt"
    )

def install_spacy_model():
    """Download and install the spaCy English language model."""
    print_section("Installing spaCy Language Model")
    
    # First check if spaCy is installed properly
    if not run_command(
        [sys.executable, "-m", "spacy", "info"],
        "Checking spaCy installation"
    ):
        print("spaCy isn't installed properly. Please install dependencies first.")
        return False
    
    # Check if model is already installed
    print("Checking if English model is already installed...")
    try:
        subprocess.run(
            [sys.executable, "-c", "import spacy; spacy.load('en_core_web_sm')"],
            check=True, capture_output=True
        )
        print("English model already installed!")
        return True
    except subprocess.CalledProcessError:
        print("English model not found. Installing...")
    
    # Install the model
    return run_command(
        [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
        "Downloading English language model"
    )

def main():
    """Main installation function."""
    print_section("SophiaAMS Installation")
    print("This script will install all required dependencies for SophiaAMS.")
    
    # Install dependencies
    if not install_dependencies():
        print("\nFailed to install dependencies. Please fix the errors and try again.")
        sys.exit(1)
    
    # Install spaCy model
    if not install_spacy_model():
        print("\nFailed to install spaCy model. You can install it manually with:")
        print("  python -m spacy download en_core_web_sm")
        sys.exit(1)
    
    print_section("Installation Complete")
    print("SophiaAMS has been successfully installed!")
    print("You can now run the system with:")
    print("  python DocumentProcessor.py")

if __name__ == "__main__":
    main() 