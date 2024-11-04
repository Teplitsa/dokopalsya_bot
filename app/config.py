from environs import Env

env = Env()
env.read_env()

BOT_TOKEN: str = env.str("BOT_TOKEN")
FACT_CHECK_TOOL: str = env.str("FACT_CHECK_TOOL", "perplexity")

GOOGLE_API_KEY = env.str("GOOGLE_API_KEY")
OPENAI_API_KEY = env.str("OPENAI_API_KEY")
PERPLEXITYAI_API_KEY = env.str("PERPLEXITYAI_API_KEY")

LANGFUSE_PUBLIC_KEY = env.str("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = env.str("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = env.str("LANGFUSE_HOST", "https://cloud.langfuse.com")

ENVIRONMENT: str = env.str("ENVIRONMENT", "NOT SET")
VERSION: str = env.str("VERSION", "NOT SET")

USE_POSTGRES: bool = env.bool("USE_POSTGRES", False)

LOG_LEVEL = env.log_level("LOG_LEVEL", "INFO")

# Add prompt caching configuration
USE_PROMPT_CACHE: bool = env.bool("USE_PROMPT_CACHE", True)  # Default to True for production

if USE_POSTGRES:
    PG_HOST: str = env.str("POSTGRES_HOST")
    PG_PORT: int = env.int("POSTGRES_PORT", 5432)
    PG_USER: str = env.str("POSTGRES_USER")
    PG_PASSWORD: str = env.str("POSTGRES_PASSWORD")
    PG_DATABASE: str = env.str("POSTGRES_DB", "tgbot")

    SQLALCHEMY_DATABASE_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"

USE_WEBHOOK: bool = env.bool("USE_WEBHOOK", False)

if USE_WEBHOOK:
    MAIN_WEBHOOK_ADDRESS: str = env.str("MAIN_WEBHOOK_ADDRESS")
    MAIN_WEBHOOK_SECRET_TOKEN: str = env.str("MAIN_WEBHOOK_SECRET_TOKEN")

    MAIN_WEBHOOK_LISTENING_HOST: str = env.str("MAIN_WEBHOOK_LISTENING_HOST")
    MAIN_WEBHOOK_LISTENING_PORT: int = env.int("MAIN_WEBHOOK_LISTENING_PORT")

    MAX_UPDATES_IN_QUEUE: int = env.int("MAX_UPDATES_IN_QUEUE", 100)

USE_CUSTOM_API_SERVER: bool = env.bool("USE_CUSTOM_API_SERVER", False)

if USE_CUSTOM_API_SERVER:
    CUSTOM_API_SERVER_IS_LOCAL: bool = env.bool("CUSTOM_API_SERVER_IS_LOCAL")
    CUSTOM_API_SERVER_BASE: str = env.str("CUSTOM_API_SERVER_BASE")
    CUSTOM_API_SERVER_FILE: str = env.str("CUSTOM_API_SERVER_FILE")

