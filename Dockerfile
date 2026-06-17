FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Hugging Face Spaces run on port 7860
EXPOSE 7860

# Set environment variables
ENV FLASK_ENV=production
ENV PORT=7860

# Create downloads folder
RUN mkdir -p downloads && chmod 777 downloads

# Run the application with gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:7860 --workers 1 --threads 8 --timeout 120 app:app"]
