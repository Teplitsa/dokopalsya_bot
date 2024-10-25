import json
from typing import List, Optional

import json_repair
import structlog
from pydantic import ValidationError

from app.constants import PromptNames
from app.models.claim_models import Claim, ExtractedClaims
from app.utils.litellm_utils import perform_litellm_completion
from app.utils.prompt_utils import get_prompt

logger = structlog.get_logger(__name__)

async def extract_claims(
    text: Optional[str], short_user_id: str
) -> List[Claim]:
    """
    Extract claims from the given text using LiteLLM.

    Args:
        text (Optional[str]): The input text from which to extract claims.
        short_user_id (str): The short user ID for tracing purposes.

    Returns:
        List[Claim]: A list of extracted Claim instances.
    """
    if not text:
        logger.warn("No text provided for claim extraction", user_id=short_user_id)
        return []

    try:
        prompt = get_prompt(PromptNames.EXTRACT_CLAIMS.value)
        if not prompt:
            logger.error(f"No prompt found for name: {PromptNames.EXTRACT_CLAIMS.value}", user_id=short_user_id)
            return []

        response = await perform_litellm_completion(
            messages=[
                {
                    "role": "user",
                    "content": text,
                },
            ],
            response_format=ExtractedClaims,
            trace_name="claim extraction",
            generation_name="extract_claims",
            trace_user_id=short_user_id,
            prompt_name=PromptNames.EXTRACT_CLAIMS,
            prompt=prompt,
        )

        if not response:
            logger.warn("No response received from LiteLLM", user_id=short_user_id)
            return []

        claims_data = response.choices[0].message.content

        if not claims_data:
            logger.warn("No claims data returned from AI model", user_id=short_user_id)
            return []

        try:
            # First, try to parse the claims_data as a JSON string
            parsed_data = json.loads(claims_data)
        except json.JSONDecodeError:
            # If that fails, try to repair the JSON
            try:
                parsed_data = json_repair.loads(claims_data)
            except Exception as je:
                logger.error("Failed to repair JSON", error=str(je), user_id=short_user_id)
                return []

        try:
            # Now try to validate the parsed data
            if isinstance(parsed_data, dict) and 'claims' in parsed_data:
                extracted_claims = ExtractedClaims.model_validate(parsed_data)
            else:
                # If the structure is not as expected, create ExtractedClaims manually
                extracted_claims = ExtractedClaims(claims=parsed_data if isinstance(parsed_data, list) else [parsed_data])

            claims = [Claim(content=claim) for claim in extracted_claims.claims]
        except ValidationError as ve:
            logger.error("Error validating claims data", error=ve, user_id=short_user_id)
            return []

        logger.info("Claims extracted", num_claims=len(claims), user_id=short_user_id)
        return claims

    except Exception as e:
        logger.error("Unexpected error extracting claims", error=str(e), user_id=short_user_id)
        return []
