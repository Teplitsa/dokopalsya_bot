from typing import Callable, Dict, List, Optional, Union
from urllib.parse import urlparse, urlunparse

from langfuse import Langfuse
from langfuse.api import Prompt_Text
from langfuse.model import TextPromptClient

from app import config
from app.constants import PromptNames
from app.models.prompt_models import PromptConfig
from app.utils.logging import get_logger

logger = get_logger("utils", "prompt_utils")

def create_prompt_text(prompt_client: TextPromptClient) -> Prompt_Text:
    return Prompt_Text(
        prompt=prompt_client.prompt,
        config=PromptConfig(**prompt_client.config).model_dump(),
        version=prompt_client.version,
        name=prompt_client.name,
        labels=prompt_client.labels,
        tags=prompt_client.tags,
    )

# Global variable to store loaded prompts
_loaded_prompts: Dict[str, Prompt_Text] = {}

def load_prompt_templates(langfuse_client: Langfuse, prompt_label: str = 'production') -> Dict[str, Prompt_Text]:
    logger.debug('Starting to load prompt templates')
    global _loaded_prompts
    _loaded_prompts = _load_prompts(langfuse_client, prompt_label)
    return _loaded_prompts

def _load_prompts(langfuse_client: Langfuse, prompt_label: str) -> Dict[str, Prompt_Text]:
    load_results = {}
    for prompt_name in PromptNames:
        try:
            # Change this line to use the synchronous version of get_prompt
            prompt_client = langfuse_client.get_prompt(
                name=prompt_name.value, label=prompt_label
            )
            if isinstance(prompt_client, TextPromptClient):
                fixed_prompt = _fix_prompt_url(prompt_client)
                load_results[prompt_name.value] = create_prompt_text(fixed_prompt)
            else:
                load_results[prompt_name.value] = f'Unexpected prompt type: {type(prompt_client)}'
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_name.value}: {str(e)}")
            load_results[prompt_name.value] = str(e)
    return _process_load_results(load_results)

def _fix_prompt_url(prompt_client: TextPromptClient) -> TextPromptClient:
    """Fix the URL in the prompt if it's missing the protocol."""
    if 'url' in prompt_client.config:
        parsed_url = urlparse(prompt_client.config['url'])
        if not parsed_url.scheme:
            fixed_url = urlunparse(('https',) + parsed_url[1:])
            prompt_client.config['url'] = fixed_url
            logger.warning(f"Fixed URL for prompt {prompt_client.name}: {fixed_url}")
    return prompt_client

def _process_load_results(load_results: Dict[str, Union[Prompt_Text, str]]) -> Dict[str, Prompt_Text]:
    prompts: Dict[str, Prompt_Text] = {}
    successful_loads: List[str] = []
    load_errors: Dict[str, str] = {}

    for prompt_name, result in load_results.items():
        if isinstance(result, Prompt_Text):
            prompts[prompt_name] = result
            successful_loads.append(prompt_name)
        else:
            load_errors[prompt_name] = result

    _log_load_results(successful_loads, load_errors)

    if not prompts:
        error_message = (
            'Failed to load any valid prompts from Langfuse. Errors encountered:\n'
            + '\n'.join(f'{k}: {v}' for k, v in load_errors.items())
        )
        logger.error(error_message)
        raise RuntimeError(error_message)

    return prompts

def _log_load_results(successful_loads: List[str], load_errors: Dict[str, str]) -> None:
    total_loaded = len(successful_loads)
    total_failed = len(load_errors)
    total_attempts = total_loaded + total_failed

    if total_loaded > 0:
        logger.info('Prompt loading completed',
                    total_loaded=total_loaded,
                    total_failed=total_failed,
                    total_attempts=total_attempts)
        logger.info('Successfully loaded prompts',
                    prompts=successful_loads)
        
        if total_failed > 0:
            logger.warning('Some prompts failed to load',
                           failed_count=total_failed,
                           failed_prompts=list(load_errors.keys()))
    else:
        logger.error('No prompts were successfully loaded',
                     total_failed=total_failed)

    # Log individual errors
    for prompt_name, error in load_errors.items():
        logger.error('Prompt load error',
                     prompt_name=prompt_name,
                     error=error)

def get_prompt(prompt_name: str) -> Optional[Prompt_Text]:
    """
    Retrieve a loaded prompt by name.
    """
    return _loaded_prompts.get(prompt_name)

def initialize_langfuse() -> Langfuse:
    """Initialize and return a Langfuse client."""
    return Langfuse(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST,
    )
