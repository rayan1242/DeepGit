# Use a slim Python 3.10 image as the base
FROM python:3.10-slim

# Install system dependencies (if needed for building some Python packages)
RUN echo "Step 1: Installing system dependencies..." && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    pkg-config \
    && rm -rf /var/lib/apt/lists/* && \
    echo "✓ System dependencies installed"

# Set the working directory in the container
WORKDIR /app

# Create logs directory
RUN echo "Step 2: Creating application directories..." && \
    mkdir -p logs && \
    echo "✓ Directories created"

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .

RUN echo "Step 3: Installing Python dependencies (this may take a few minutes)..." && \
    pip install --upgrade pip setuptools wheel build >/dev/null 2>&1 && \
    pip install torch==2.0.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt && \
    echo "✓ Python dependencies installed"

# Copy the rest of the code into the container
RUN echo "Step 4: Copying application code..."
COPY . .
RUN echo "✓ Application code copied"

# Environment variables for logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the default port for Gradio
EXPOSE 7860

RUN echo "✓ Docker image build complete!"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:7860/status', timeout=5)" || exit 1

# Set the command to run your app
CMD ["python", "-u", "app.py"]