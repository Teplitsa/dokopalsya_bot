from pydantic import BaseModel


class PromptConfig(BaseModel):
    model: str
    temperature: float
