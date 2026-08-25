# Dockerfile for a Django application with Gunicorn

# Stage 1: Build the application
# Use the official Python runtime image
FROM python:3.13-slim AS builder

# Set the working directory inside the container
RUN mkdir /app

# Set the working directory
WORKDIR /app

# Update system packages to address vulnerabilities
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
# Prevents Python from writing pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
#Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Upgrade pip
RUN pip install --upgrade pip
# Copy the requirements file first (better caching)
COPY requirements.txt /app/
# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Create the final image
FROM python:3.13-slim

# Create a non-root user and switch to it
RUN addgroup --gid 1000 appuser && \
    adduser --disabled-password --gecos '' --uid 1000 --gid 1000 appuser && \
    mkdir /app && \
    chown -R appuser:appuser /app

# Copy the installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set working directory
WORKDIR /app

# Copy the Django project files into the container
COPY --chown=appuser:appuser . .

# Set environment variables
# Prevents Python from writing pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
#Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Run the Django development server
CMD ["/app/entrypoint.sh"]
