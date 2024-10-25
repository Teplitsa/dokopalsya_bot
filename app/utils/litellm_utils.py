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

async def perform_litellm_completion(
    messages: List[Dict[str, str]],
    trace_name: str,
    generation_name: str,
    trace_user_id: str = "",
    prompt_name: Optional[PromptNames] = None,
    prompt: Optional[Prompt_Text] = None,
    response_format: Optional[Any] = None,
) -> Any:
    """
    Perform a completion using LiteLLM with error handling and logging.

    Args:
        messages (List[Dict[str, str]]): The messages for the completion.
        trace_name (str): The name of the trace for logging.
        generation_name (str): The name of the generation for logging.
        trace_user_id (str, optional): The user ID for tracing purposes.
        prompt_name (PromptNames, optional): The name of the prompt to use.
        prompt (Prompt_Text, optional): The loaded prompt to use.
        response_format (Any, optional): The expected response format.

    Returns:
        Any: The completion response.

    Raises:
        Exception: If an unexpected error occurs during completion.
    """
    try:
        trace_id = str(uuid.uuid4())
        generation_id = str(uuid.uuid4())
        tags = [ENVIRONMENT] if ENVIRONMENT and isinstance(ENVIRONMENT, str) else []

        if not prompt:
            prompt = get_prompt(prompt_name.value) if prompt_name else None

        if not prompt:
            logger.error(f"No prompt found for name: {prompt_name}")
            return None

        # Prepare system message with prompt content
        system_message = {"role": "system", "content": prompt.prompt}
        full_messages = [system_message] + messages

        completion_kwargs = {
            "model": prompt.config["model"],
            "messages": full_messages,
            "temperature": prompt.config["temperature"],
            "metadata": {
                "trace_name": trace_name,
                "generation_name": generation_name,
                "generation_id": generation_id,
                "trace_id": trace_id,
                "trace_user_id": trace_user_id,
                "tags": tags,
                "prompt": prompt.dict(exclude_unset=False),
                "version": VERSION,
            },
        }

        if response_format:
            completion_kwargs["response_format"] = response_format

        response = await acompletion(**completion_kwargs)

        return response

    except APIConnectionError as e:
        logger.error(f"LiteLLM connection error during {trace_name}", error=str(e))
    except AuthenticationError as e:
        logger.error(f"LiteLLM authentication error during {trace_name}", error=str(e))
    except BadRequestError as e:
        logger.error(f"LiteLLM bad request error during {trace_name}", error=str(e))
    except RateLimitError as e:
        logger.error(f"LiteLLM rate limit error during {trace_name}", error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during {trace_name}", error=str(e))
        raise

    return None
