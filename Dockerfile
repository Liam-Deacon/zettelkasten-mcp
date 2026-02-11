FROM python:3.11-slim

# Set working directory
WORKDIR /app

# BuildKit automatically sets this for each platform build.
ARG TARGETARCH

# Install system dependencies for optional database drivers.
# SQL Server ODBC packages are installed on amd64 only.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        gnupg2 \
        ca-certificates \
        apt-transport-https \
        dpkg; \
    if [ "${TARGETARCH}" = "amd64" ]; then \
        curl --fail --show-error --location --output /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb; \
        dpkg -i /tmp/packages-microsoft-prod.deb; \
        rm -f /tmp/packages-microsoft-prod.deb; \
        apt-get update; \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
            msodbcsql18 \
            unixodbc; \
    else \
        echo "Skipping SQL Server ODBC installation for TARGETARCH=${TARGETARCH}"; \
    fi; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY . .
RUN set -eux; \
    if [ "${TARGETARCH}" = "amd64" ]; then \
        pip install --no-cache-dir .[postgresql,sqlserver,mysql]; \
    else \
        pip install --no-cache-dir .[postgresql,mysql]; \
        echo "Installed without sqlserver extra for TARGETARCH=${TARGETARCH}"; \
    fi

# Set environment variables
ENV ZETTELKASTEN_NOTES_DIR=/data/notes
ENV ZETTELKASTEN_DATABASE=/data/db/zettelkasten.db
ENV ZETTELKASTEN_LOG_LEVEL=DEBUG

# Create necessary directories
RUN mkdir -p /data/notes /data/db

# FastMCP HTTP transport configuration (Smithery will see these)
ENV FASTMCP_TRANSPORT=sse
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
EXPOSE 8000

# Set the entry point
ENTRYPOINT ["zettelkasten-mcp"]
