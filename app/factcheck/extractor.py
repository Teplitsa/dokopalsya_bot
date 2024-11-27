import json
from typing import List, Optional

import json_repair
import structlog
from pydantic import ValidationError

from app.constants import PromptNames
from app.models.claim_models import Claim, ExtractedClaims
from app.utils.litellm_utils import generate_observation_id, perform_litellm_completion
from app.utils.prompt_utils import get_prompt

logger = structlog.get_logger(__name__)

async def extract_claims(
    text: Optional[str], 
    short_user_id: str,
    trace_id: str,
) -> List[Claim]:
    """
    Extract claims from the given text using LiteLLM.

    Args:
        text (Optional[str]): The input text from which to extract claims.
        short_user_id (str): The short user ID for tracing purposes.
        trace_id (str): The trace ID for the fact-check session.

    Returns:
        List[Claim]: A list of extracted Claim instances.
    """
    # Generate a parent observation ID for all extraction attempts
    extraction_parent_id = generate_observation_id("extract")
    
    logger.info("Starting claims extraction", 
                trace_id=trace_id, 
                user_id=short_user_id,
                parent_observation_id=extraction_parent_id,
    )

    if not text:
        logger.warn("No text provided for claim extraction", 
                   trace_id=trace_id, 
                   user_id=short_user_id)
        return []

    try:
        prompt = get_prompt(PromptNames.EXTRACT_CLAIMS.value)
        if not prompt:
            logger.error(f"No prompt found for name: {PromptNames.EXTRACT_CLAIMS.value}", 
                        trace_id=trace_id, 
                        user_id=short_user_id)
            return []

        response = await perform_litellm_completion(
            messages=[{"role": "user", "content": text}],
            response_format=ExtractedClaims,
            trace_name="claim_extraction",
            generation_name="extract_claims",
            trace_user_id=short_user_id,
            trace_id=trace_id,
            prompt_name=PromptNames.EXTRACT_CLAIMS,
            prompt=prompt,
            parent_observation_id=extraction_parent_id
        )

        if not response:
            logger.warn("No response received from LiteLLM", 
                       user_id=short_user_id, 
                       trace_id=trace_id)
            return []

        claims_data = response.choices[0].message.content

        if not claims_data:
            logger.warn("No claims data returned from AI model", 
                       user_id=short_user_id,
                       trace_id=trace_id)
            return []

        try:
            parsed_data = json.loads(claims_data)
        except json.JSONDecodeError:
            try:
                parsed_data = json_repair.loads(claims_data)
            except Exception as je:
                logger.error("Failed to repair JSON", 
                           error=str(je), 
                           user_id=short_user_id,
                           trace_id=trace_id)
                return []

        try:
            if isinstance(parsed_data, dict) and 'claims' in parsed_data:
                extracted_claims = ExtractedClaims.model_validate(parsed_data)
            else:
                extracted_claims = ExtractedClaims(claims=parsed_data if isinstance(parsed_data, list) else [parsed_data])

            claims = [Claim(content=claim) for claim in extracted_claims.claims]
        except ValidationError as ve:
            logger.error("Error validating claims data", 
                        error=ve, 
                        user_id=short_user_id,
                        trace_id=trace_id)
            return []

        logger.info("Claims extracted", 
                   num_claims=len(claims), 
                   user_id=short_user_id,
                   trace_id=trace_id,
                   parent_observation_id=extraction_parent_id)
        return claims

    except Exception as e:
        logger.error("Unexpected error extracting claims", 
                    error=str(e), 
                    user_id=short_user_id,
                    trace_id=trace_id,
                    parent_observation_id=extraction_parent_id)
        return []
