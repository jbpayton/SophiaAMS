#!/bin/bash

echo "🚀 Setting up SophiaAMS Web Interface..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js version: $(node --version)"

# Install server dependencies
echo ""
echo "📦 Installing server dependencies..."
cd server
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install server dependencies"
    exit 1
fi

# Install client dependencies
echo ""
echo "📦 Installing client dependencies..."
cd ../client
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install client dependencies"
    exit 1
fi

cd ..

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Make sure Python API server is running:"
echo "     python api_server.py"
echo ""
echo "  2. Start Node.js server (in new terminal):"
echo "     cd server && npm start"
echo ""
echo "  3. Start React client (in new terminal):"
echo "     cd client && npm run dev"
echo ""
echo "  4. Open browser to http://localhost:3000"
echo ""
