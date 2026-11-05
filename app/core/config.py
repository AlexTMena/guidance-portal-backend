import os

APP_ENV = os.getenv("APP_ENV", "production").lower()
DATABASE_NAME = os.getenv("MONGODB_DATABASE", "guidance_portal")
API_TOKEN_ISSUER = os.getenv("API_TOKEN_ISSUER", "guidance-portal-frontend")
API_TOKEN_AUDIENCE = os.getenv("API_TOKEN_AUDIENCE", "guidance-portal-api")
DOCS_ENABLED = APP_ENV == "development"
