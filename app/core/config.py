from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Product Parsing Service"
    MONGODB_URL: str = "mongodb://mongo:27017"
    DATABASE_NAME: str = "parser_db"
    
    class Config:
        env_file = ".env"

settings = Settings()
