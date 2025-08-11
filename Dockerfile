ARG CONTAINERPORT_API
# Stage 1: Build the Next.js frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend

ARG CONTAINERPORT_API
ENV NEXT_PUBLIC_CONTAINERPORT_API=$CONTAINERPORT_API

COPY frontend/package*.json ./
RUN npm install
COPY frontend ./
RUN npm run build

# Stage 2: Setup Python environment and install dependencies
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    nodejs \
    npm \
    default-libmysqlclient-dev \
    netcat-openbsd \
    pkg-config \
    build-essential \
    libmagic1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    poppler-utils \
    git \
    cmake \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install packages
# Note: scipy is now a direct dependency
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Detectron2 separately
RUN pip install --no-cache-dir 'git+https://github.com/facebookresearch/detectron2.git'

# Pre-download and cache the layout model to a non-volume-mounted path.
RUN mkdir -p /models
RUN wget -O /models/publaynet_config.yml "https://www.dropbox.com/s/f3b12qc4hc0yh4m/config.yml?dl=1"
RUN wget -O /models/publaynet_model.pth "https://www.dropbox.com/s/dgy9c10wykk4lq4/model_final.pth?dl=1"

# Copy application code
COPY . .

# Copy the built frontend from the builder stage
COPY --from=frontend-builder /app/frontend/.next ./frontend/.next
COPY --from=frontend-builder /app/frontend/public ./frontend/public

# Copy entrypoint script to a location that won't be overwritten by a volume mount
COPY entrypoint.sh /usr/local/bin/
# Make entrypoint script executable
RUN chmod +x /usr/local/bin/entrypoint.sh

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports for backend and frontend
EXPOSE ${CONTAINERPORT_API:-8000}
EXPOSE ${CONTAINERPORT_FRONTEND:-3000}

# Set the entrypoint script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"] 