# Remove all compiled Python files (*.pyc)

find . -type f -name "../apps/*.pyc" -delete

# Remove all __pycache__ folders recursively
find . -type d -name "../apps/__pycache__" -exec rm -rf {} +

# Remove all migration files except __init__.py
find . -path "../apps/*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "../apps/*/migrations/*.pyc" -delete
