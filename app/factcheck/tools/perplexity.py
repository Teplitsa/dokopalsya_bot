import json
from datetime import UTC, datetime
from typing import Optional

import json_repair
from pydantic import ValidationError

from app.constants import PromptNames
from app.models.claim_models import (
    Claim,
    PerplexityClaimReview,
    VerificationResult,
)
from app.utils.litellm_utils import perform_litellm_completion
from app.utils.logging import get_logger
from app.utils.prompt_utils import get_prompt

logger = get_logger('factcheck', 'perplexity')

MAX_RETRIES = 3

async def perplexity_claim_check(claim: Claim, short_user_id: str) -> VerificationResult:
    """
    Check a single claim using perplexity fact-check service via LiteLLM.

    Args:
        claim (Claim): The claim to be verified.
        short_user_id (str): The short user ID generated from the message object.

    Returns:
        VerificationResult: The result of the claim verification.
    """
    prompt = get_prompt(PromptNames.PERPLEXITY_FACT_CHECK.value)
    if not prompt:
        logger.error(f'No prompt found for name: {PromptNames.PERPLEXITY_FACT_CHECK.value}', 
                     claim_id=str(claim.id), user_id=short_user_id)
        return create_verification_result(claim, error='Prompt not found')

    try:
        perplexity_claim_review = await get_perplexity_claim_reviews(claim, short_user_id, prompt)
        return create_verification_result(claim, perplexity_claim_reviews=perplexity_claim_review)
    except Exception as e:
        error = f'Error during fact-check: {str(e)}'
        logger.error('Error during perplexity fact-check', 
                     error=error, claim_id=str(claim.id), user_id=short_user_id)
        return create_verification_result(claim, error=error)

def parse_raw_content(raw_content: str) -> dict:
    try:
        parsed_content = json_repair.loads(raw_content)
        PerplexityClaimReview(**parsed_content)  # Validate the structure
        return parsed_content
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse raw content: {str(e)}") from e
    except ValidationError as ve:
        raise ValueError(f"Failed to validate parsed content: {str(ve)}") from ve

async def get_perplexity_claim_reviews(claim: Claim, short_user_id: str, prompt: str) -> PerplexityClaimReview:
    for attempt in range(MAX_RETRIES):
        try:
            response = await perform_litellm_completion(
                messages=[
                    {'role': 'user', 'content': f'Claim: {claim.content}'},
                ],
                trace_name='perplexity_fact_check',
                generation_name='claim_verification',
                trace_user_id=short_user_id,
                prompt_name=PromptNames.PERPLEXITY_FACT_CHECK,
                prompt=prompt,
            )
            
            if response and response.choices:
                raw_content = response.choices[0].message.content
                logger.info('Perplexity fact-check raw response', 
                            response=raw_content, 
                            claim_id=str(claim.id), user_id=short_user_id)
                
                try:
                    validated_result = parse_raw_content(raw_content)
                    return PerplexityClaimReview(**validated_result)
                except ValueError as e:
                    logger.error(f'Error parsing or validating response (Attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}', 
                                 claim_id=str(claim.id), user_id=short_user_id)
                    if attempt == MAX_RETRIES - 1:
                        raise
                    continue  # Retry on parsing or validation error
            
            logger.warning(f'No valid response (Attempt {attempt + 1}/{MAX_RETRIES}). Retrying...', 
                           claim_id=str(claim.id), user_id=short_user_id)
        except Exception as e:
            logger.error(f'Error during fact-check (Attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}', 
                         claim_id=str(claim.id), user_id=short_user_id)
            if attempt == MAX_RETRIES - 1:
                raise
    
    raise ValueError(f'No valid response from fact-check service after {MAX_RETRIES} attempts')

def create_verification_result(claim: Claim, perplexity_claim_reviews: Optional[PerplexityClaimReview] = None, error: Optional[str] = None) -> VerificationResult:
    return VerificationResult(
        claim_id=str(claim.id),
        claim=claim.content,
        google_claim_reviews=None,
        perplexity_claim_reviews=perplexity_claim_reviews,
        error=error,
        verified_at=datetime.now(UTC),
    )
