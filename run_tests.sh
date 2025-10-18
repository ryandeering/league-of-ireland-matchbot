#!/bin/bash
# Test runner script for matchbot

set -e

echo "=========================================="
echo "League of Ireland Matchbot - Test Suite"
echo "=========================================="
echo ""

# Check if pytest is installed
if ! command -v python3 -m pytest &> /dev/null; then
    echo "⚠️  pytest not found. Installing..."
    pip install pytest pytest-cov
fi

# Run live score tests
echo "📊 Running live score tests..."
python3 -m pytest tests/test_live_scores.py -v

# Run cache tests
echo ""
echo "💾 Running cache tests..."
python3 -m pytest tests/test_cache.py -v

# Run live updater integration tests
echo ""
echo "🔄 Running live updater integration tests..."
python3 -m pytest tests/test_live_updater.py -v

# Run all tests with coverage
echo ""
echo "📈 Running all tests with coverage..."
python3 -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

# PEP8 linting
echo ""
echo "✅ Checking code quality with pylint..."
python3 -m pylint common.py premier_division.py first_division.py \
    fai_cup.py live_updater.py --exit-zero | grep "rated at"

echo ""
echo "=========================================="
echo "✅ All tests completed!"
echo "=========================================="
echo ""
echo "Coverage report: htmlcov/index.html"
