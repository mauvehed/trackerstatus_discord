# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy project metadata files first
COPY pyproject.toml poetry.lock README.md ./

# Copy config file with default empty configuration
COPY config.json ./

# Copy source code
COPY trackerstatus_discord/ ./trackerstatus_discord/
COPY main.py ./

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install dependencies (production only)
RUN /root/.local/bin/poetry install --only main

# Run the bot
CMD ["/root/.local/bin/poetry", "run", "python", "main.py"] 