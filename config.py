import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production-please")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ai_chat:ai_chat@localhost:5432/ai_chat")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".txt", ".md", ".py", ".js", ".json", ".csv", ".pdf"}

# Default Admin Configuration (Used only for initial DB setup)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
ADMIN_API_BASE = os.getenv("ADMIN_API_BASE", "")
