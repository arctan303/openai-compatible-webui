import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production-please")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/chat.db")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".txt", ".md", ".py", ".js", ".json", ".csv", ".pdf"}

# Bootstrap Configuration (Used only for first-time DB setup)
BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", os.getenv("ADMIN_USERNAME", "admin"))
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", "admin123"))
BOOTSTRAP_SYSTEM_API_KEY = os.getenv("BOOTSTRAP_SYSTEM_API_KEY", os.getenv("ADMIN_API_KEY", ""))
BOOTSTRAP_SYSTEM_API_BASE = os.getenv("BOOTSTRAP_SYSTEM_API_BASE", os.getenv("ADMIN_API_BASE", "https://api.openai.com/v1"))
BOOTSTRAP_SYSTEM_MODEL = os.getenv("BOOTSTRAP_SYSTEM_MODEL", "gpt-4o")
SETUP_WIZARD_ENABLED = os.getenv("SETUP_WIZARD_ENABLED", "true").lower() == "true"
