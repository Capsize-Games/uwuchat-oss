"""Production-mode preset — PostgreSQL multi-tenant, debug off."""

DEPLOYMENT_MODE = "production"
DEBUG = False
DATABASE_BACKEND = "postgresql"
DB_TENANCY_MODE = "multi"
# Containerized deployment: the process must bind all interfaces
# inside its own container network namespace (Docker port-publishing
# + a reverse proxy are the real network boundary). server_thread.py
# refuses to actually start serving on a non-loopback host unless
# AIRUNNER_API_KEY is set or AIRUNNER_INSECURE_NO_AUTH=1 -- this
# preset sets AIRUNNER_INSECURE_NO_AUTH="0" below, so a real API key
# (or the auth extension) is required regardless of bind address.
AIRUNNER_SERVER_HOST = "0.0.0.0"  # nosec B104
AIRUNNER_SERVER_PORT = 8080
AIRUNNER_INSECURE_NO_AUTH = "0"
