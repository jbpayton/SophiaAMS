#!/usr/bin/env python3

import subprocess
import sys
import os
from setuptools import setup, find_packages

# Read requirements
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

# Setup configuration
setup(
    name="SophiaAMS",
    version="0.1.0",
    description="Associative Semantic Memory System",
    packages=find_packages(),
    install_requires=requirements,
)

# Install spaCy model after setup
def install_spacy_model():
    print("Installing spaCy English language model...")
    try:
        # Check if the model is already installed
        subprocess.check_call([sys.executable, "-m", "spacy", "validate"])
        print("spaCy model already installed.")
    except subprocess.CalledProcessError:
        # Install the model
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        print("spaCy model installed successfully.")
    except Exception as e:
        print(f"Error validating spaCy models: {e}")
        print("Attempting to install model anyway...")
        try:
            subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
            print("spaCy model installed successfully.")
        except Exception as e:
            print(f"Error installing spaCy model: {e}")
            print("Please install it manually with: python -m spacy download en_core_web_sm")

# Run the spaCy model installation if this script is executed directly
if __name__ == "__main__":
    install_spacy_model() 