from enum import Enum


class PromptNames(str, Enum):
    EXTRACT_CLAIMS = 'extract_claims'
    PERPLEXITY_FACT_CHECK = 'perplexity_fact_check'
    # Add other prompt names here as needed
