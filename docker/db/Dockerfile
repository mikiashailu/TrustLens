# Postgres image for TrustLens (same defaults can be overridden in docker-compose)
FROM postgres:16-alpine

ENV POSTGRES_USER=trustlens \
    POSTGRES_PASSWORD=trustlens \
    POSTGRES_DB=trustlens

# Optional: add scripts to docker-entrypoint-initdb.d/ for seed data
# COPY ./init/*.sql /docker-entrypoint-initdb.d/

EXPOSE 5432
