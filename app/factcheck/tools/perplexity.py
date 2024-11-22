import json
from datetime import UTC, datetime
from typing import List, Optional

import json_repair
from pydantic import ValidationError

from app.constants import PromptNames
from app.models.claim_models import (
    Claim,
    PerplexityClaimsReview,
    VerificationResult,
)
from app.utils.litellm_utils import generate_observation_id, perform_litellm_completion
from app.utils.logging import get_logger
from app.utils.prompt_utils import get_prompt

logger = get_logger('factcheck', 'perplexity')

MAX_RETRIES = 3

async def perplexity_claim_check(claim: Claim, short_user_id: str, trace_id: str) -> VerificationResult:
    """
    Check a single claim using perplexity fact-check service via LiteLLM.

    Args:
        claim (Claim): The claim to be verified.
        short_user_id (str): The short user ID generated from the message object.
        trace_id (str): The trace ID for the fact-check session.

    Returns:
        VerificationResult: The result of the claim verification.
    """
    # Generate a parent observation ID for all perplexity attempts for this claim
    perplexity_parent_id = generate_observation_id("perplexity")
    
    logger.info("Starting perplexity claim check", 
                trace_id=trace_id, 
                claim_id=str(claim.id),
                parent_observation_id=perplexity_parent_id)

    prompt = get_prompt(PromptNames.PERPLEXITY_FACT_CHECK.value)
    if not prompt:
        logger.error(f'No prompt found for name: {PromptNames.PERPLEXITY_FACT_CHECK.value}', claim_id=str(claim.id), user_id=short_user_id, trace_id=trace_id)
        return create_verification_result(claim, error='Prompt not found')

    try:
        perplexity_claims_review = await get_perplexity_claim_reviews(
            claim, 
            short_user_id, 
            trace_id, 
            prompt,
            parent_observation_id=perplexity_parent_id  # Pass the parent ID
        )
        if not perplexity_claims_review.claim_reviews:
            return create_verification_result(claim, error='No claim reviews returned')
            
        return create_verification_result(claim, perplexity_claim_reviews=perplexity_claims_review)
    except Exception as e:
        error = f'Error during fact-check: {str(e)}'
        logger.error('Error during perplexity fact-check', error=error, claim_id=str(claim.id), user_id=short_user_id, trace_id=trace_id)
        return create_verification_result(claim, error=error)

def parse_raw_content(raw_content: str, citations: Optional[List[str]] = None) -> PerplexityClaimsReview:
    """
    Parse and validate the raw content from the LLM response.
    
    Args:
        raw_content (str): Raw JSON string from LLM
        citations (Optional[List[str]]): List of citation URLs from the response
        
    Returns:
        PerplexityClaimsReview: Validated claim review object
        
    Raises:
        ValueError: If parsing or validation fails
    """
    try:
        parsed_content = json_repair.loads(raw_content)
        if not isinstance(parsed_content, dict) or 'claim_reviews' not in parsed_content:
            raise ValueError("Response missing required 'claim_reviews' field")
            
        if citations:
            parsed_content['citations'] = citations
            
        return PerplexityClaimsReview(**parsed_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse raw content: {str(e)}") from e
    except ValidationError as ve:
        raise ValueError(f"Failed to validate parsed content: {str(ve)}") from ve

async def get_perplexity_claim_reviews(
    claim: Claim, 
    short_user_id: str, 
    trace_id: str,
    prompt: str,
    parent_observation_id: Optional[str] = None
) -> PerplexityClaimsReview:
    """Get claim reviews from Perplexity service."""
    for attempt in range(MAX_RETRIES):
        try:
            response = await perform_litellm_completion(
                messages=[
                    {'role': 'user', 'content': f'Claim: {claim.content}'},
                ],
                trace_name='perplexity_fact_check',
                generation_name='claim_verification',
                trace_user_id=short_user_id,
                trace_id=trace_id,
                prompt_name=PromptNames.PERPLEXITY_FACT_CHECK,
                prompt=prompt,
                parent_observation_id=parent_observation_id
            )
            
            if response and response.choices:
                raw_content = response.choices[0].message.content
                citations = response.citations if hasattr(response, 'citations') else None
                
                logger.info('Perplexity fact-check raw response', 
                          response=raw_content,
                          citations=citations, 
                          claim_id=str(claim.id), 
                          user_id=short_user_id,
                          trace_id=trace_id)
                
                try:
                    return parse_raw_content(raw_content, citations)
                except ValueError as e:
                    logger.error(
                        f'Error parsing or validating response (Attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}',
                        claim_id=str(claim.id),
                        user_id=short_user_id,
                        trace_id=trace_id
                    )
                    if attempt == MAX_RETRIES - 1:
                        raise
                    continue
            
            logger.warning(
                f'No valid response (Attempt {attempt + 1}/{MAX_RETRIES}). Retrying...',
                claim_id=str(claim.id),
                user_id=short_user_id,
                trace_id=trace_id
            )
        except Exception as e:
            logger.error(
                f'Error during fact-check (Attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}',
                claim_id=str(claim.id),
                user_id=short_user_id,
                trace_id=trace_id
            )
            if attempt == MAX_RETRIES - 1:
                raise
    
    raise ValueError(f'No valid response from fact-check service after {MAX_RETRIES} attempts')

def create_verification_result(
    claim: Claim, 
    perplexity_claim_reviews: Optional[PerplexityClaimsReview] = None, 
    error: Optional[str] = None
) -> VerificationResult:
    """
    Create a verification result from the claim and perplexity reviews.
    
    Args:
        claim (Claim): The original claim
        perplexity_claim_reviews (Optional[PerplexityClaimsReview]): The perplexity review results
        error (Optional[str]): Any error message
        
    Returns:
        VerificationResult: The complete verification result
    """
    return VerificationResult(
        claim_id=str(claim.id),
        claim=claim.content,
        google_claim_reviews=None,
        perplexity_claim_reviews=perplexity_claim_reviews,
        error=error,
        verified_at=datetime.now(UTC),
    )
