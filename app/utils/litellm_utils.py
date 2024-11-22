import uuid
from typing import Any, Dict, List, Optional

import litellm
from langfuse.model import Prompt_Text
from litellm import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    acompletion,
)

from app.config import ENVIRONMENT, VERSION
from app.constants import PromptNames
from app.utils.logging import get_logger
from app.utils.prompt_utils import get_prompt

logger = get_logger("utils", "litellm")

litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

def generate_observation_id(prefix: str) -> str:
    """Generate a unique observation ID with a prefix.
    
    Args:
        prefix (str): Prefix to identify the type of observation (e.g., 'extract', 'perplexity')
        
    Returns:
        str: A unique observation ID
    """
    return f"{prefix}-{str(uuid.uuid4())}"

async def perform_litellm_completion(
    messages: List[Dict[str, str]],
    trace_name: str,
    generation_name: str,
    trace_user_id: str = "",
    trace_id: Optional[str] = None,
    prompt_name: Optional[PromptNames] = None,
    prompt: Optional[Prompt_Text] = None,
    response_format: Optional[Any] = None,
    return_citations: bool = False,
    parent_observation_id: Optional[str] = None,
) -> Any:
    """
    Perform a completion using LiteLLM with error handling and logging.

    Args:
        messages (List[Dict[str, str]]): The messages for the completion.
        trace_name (str): The name of the trace for logging.
        generation_name (str): The name of the generation for logging.
        trace_user_id (str, optional): The user ID for tracing purposes.
        trace_id (str, optional): The trace ID for the fact-check session.
        prompt_name (PromptNames, optional): The name of the prompt to use.
        prompt (Prompt_Text, optional): The loaded prompt to use.
        response_format (Any, optional): The expected response format.
        return_citations (bool, optional): Whether to return citations.
        parent_observation_id (str, optional): The parent observation ID for tracing purposes.

    Returns:
        Any: The completion response.
    """
    try:
        trace_id = trace_id or str(uuid.uuid4())
        generation_id = str(uuid.uuid4())
        
        tags = [ENVIRONMENT] if ENVIRONMENT and isinstance(ENVIRONMENT, str) else []

        if not prompt:
            prompt = get_prompt(prompt_name.value) if prompt_name else None

        if not prompt:
            logger.error(f"No prompt found for name: {prompt_name}", trace_id=trace_id)
            return None

        system_message = {"role": "system", "content": prompt.prompt}
        full_messages = [system_message] + messages

        metadata = {
            "trace_name": trace_name,
            "generation_name": generation_name,
            "generation_id": generation_id,
            "trace_id": trace_id,
            "trace_user_id": trace_user_id,
            "tags": tags,
            "prompt": prompt.dict(exclude_unset=False),
            "version": VERSION,
            "parent_observation_id": parent_observation_id,
        }

        completion_kwargs = {
            "model": prompt.config["model"],
            "messages": full_messages,
            "temperature": prompt.config["temperature"],
            "metadata": metadata,
        }

        if response_format:
            completion_kwargs["response_format"] = response_format

        model = prompt.config["model"].lower()
        if return_citations and any(provider in model for provider in ["anthropic", "claude"]):
            completion_kwargs["return_citations"] = return_citations

        logger.debug("Performing LiteLLM completion", trace_id=trace_id, generation_id=generation_id, model=model)

        response = await acompletion(**completion_kwargs)

        logger.debug("LiteLLM completion successful", trace_id=trace_id, generation_id=generation_id)

        return response

    except APIConnectionError as e:
        logger.error(f"LiteLLM connection error during {trace_name}",
                    error=str(e),
                    trace_id=trace_id)
    except AuthenticationError as e:
        logger.error(f"LiteLLM authentication error during {trace_name}",
                    error=str(e),
                    trace_id=trace_id)
    except BadRequestError as e:
        logger.error(f"LiteLLM bad request error during {trace_name}",
                    error=str(e),
                    trace_id=trace_id)
    except RateLimitError as e:
        logger.error(f"LiteLLM rate limit error during {trace_name}",
                    error=str(e),
                    trace_id=trace_id)
    except Exception as e:
        logger.error(f"Unexpected error during {trace_name}",
                    error=str(e),
                    trace_id=trace_id)
        raise

    return None
