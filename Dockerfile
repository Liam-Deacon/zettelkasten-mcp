FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for optional database drivers (incl. SQL Server ODBC)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        gnupg2 \
        ca-certificates \
        apt-transport-https; \
    curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft-prod.gpg; \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/microsoft-prod.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
        unixodbc; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY . .
RUN pip install --no-cache-dir .[postgresql,sqlserver,mysql]

# Set environment variables
ENV ZETTELKASTEN_NOTES_DIR=/data/notes
ENV ZETTELKASTEN_DATABASE=/data/db/zettelkasten.db
ENV ZETTELKASTEN_LOG_LEVEL=DEBUG

# Create necessary directories
RUN mkdir -p /data/notes /data/db

# FastMCP HTTP transport configuration (Smithery will set these)
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
EXPOSE 8000

# Set the entry point
ENTRYPOINT ["zettelkasten-mcp"]
