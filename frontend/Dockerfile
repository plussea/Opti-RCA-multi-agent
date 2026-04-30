# Single-stage: runs the pre-built Next.js standalone.
# Node.js is installed from NodeSource (no external image dependency).
FROM python:3.9-slim

WORKDIR /app

# Install Node.js 20 from NodeSource + wget (used by docker healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl wget \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy pre-built Next.js standalone output
COPY .next/standalone ./
COPY .next/static ./.next/static

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV NODE_ENV=production

CMD ["node", "server.js"]
