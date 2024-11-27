import re
import uuid

from aiogram import F, Router, flags
from aiogram.filters import Command, CommandStart
from aiogram.types import LinkPreviewOptions, Message

from app.factcheck import process_fact_check_session
from app.factcheck.extractor import extract_claims
from app.models.claim_models import FactCheckSession
from app.utils.logging import get_logger
from app.utils.message_utils import messages
from app.utils.user_utils import generate_short_user_id

router = Router()

logger = get_logger("handlers", "messages")


@router.message(CommandStart())
async def process_start_command(message: Message) -> None:
    logger.debug('Start command received', user_id=message.from_user.id)
    await message.answer(messages['start_command']['welcome_text'], parse_mode="HTML")


@router.message(Command(commands="info"))
@flags.chat_action("typing")
async def process_info_command(message: Message) -> None:
    logger.debug('Info command received', user_id=message.from_user.id)
    await message.answer(messages['info_command']['info_text'], parse_mode="HTML")


@flags.chat_action("typing")
@router.message(Command(commands=re.compile(r".*")))
async def process_other_commands(message: Message) -> None:
    logger.debug('Other command received', user_id=message.from_user.id, command=message.text)
    await message.answer(messages['other_commands']['default_response'])


@router.message(F.text | F.caption)
@flags.chat_action("typing")
async def message(message: Message) -> None:
    """
    Handle incoming messages.
    """
    # Generate trace_id at the start of message processing
    trace_id = str(uuid.uuid4())
    short_user_id = generate_short_user_id(message.from_user.id)
    
    text = message.text or message.caption or ""
    logger.info('Processing message', user_id=short_user_id, text_length=len(text))

    session = FactCheckSession(original_text=text, user_id=short_user_id)
    
    # Extract claims
    claims = await extract_claims(text, short_user_id, trace_id)
    session.claims = claims

    if not claims:
        logger.info('No claims found in message', user_id=short_user_id)
        await message.reply(
            messages['fact_check']['no_claims'],
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        return

    # Send intermediate message with extracted claims
    claims_message = (
        messages['fact_check']['claims_found_single'] if len(claims) == 1 
        else messages['fact_check']['claims_found_multiple']
    )

    for idx, claim in enumerate(claims, start=1):
        if len(claims) > 1:
            claims_message += f"{idx}. <b>{claim.content}</b>\n"
        else:
            claims_message += f"<b>{claim.content}</b>\n"
    claims_message += messages['fact_check']['checking_continue']

    await message.reply(claims_message, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))

    # Continue with fact-checking process
    processed_session = await process_fact_check_session(session, short_user_id, trace_id)

    # Prepare response based on verification_results
    response_lines = [messages['fact_check']['results_header']]
    
    total_claims = len(processed_session.claims)
    for idx, claim in enumerate(processed_session.claims, start=1):
        results = [
            r
            for r in processed_session.verification_results
            if r.claim_id == str(claim.id)
        ]
        if results:
            for result in results:
                # Add claim with number only if there are multiple claims
                if total_claims > 1:
                    response_lines.append(f"\n{idx}. <b>{claim.content}</b>\n")
                else:
                    response_lines.append(f"\n<b>{claim.content}</b>\n")
                
                if result.google_claim_reviews:
                    review = result.google_claim_reviews[0]
                    verdict = review.textual_rating
                    source = review.publisher.get("site", messages['fact_check']['unknown_source'])
                    response_lines.append(f"{messages['fact_check']['verdict_label']} {verdict}")
                    response_lines.append(f"{messages['fact_check']['source_label']} <a href='{review.url}'>{source}</a>")
                
                if result.perplexity_claim_reviews and result.perplexity_claim_reviews.claim_reviews:
                    review = result.perplexity_claim_reviews.claim_reviews[0]
                    if review:
                        # Access the verification details using the correct model structure
                        verification = review.verification
                        response_lines.append(f"{messages['fact_check']['conclusion_label']} {verification.conclusion}")
                        
                        if verification.source:
                            response_lines.append("\n")
                            response_lines.append(messages['fact_check']['sources_header'])
                            # Add sources with their content and URLs
                            for source in verification.source:
                                if source.url:
                                    response_lines.append(f"<a href='{source.url}'>{source.name}</a>")
                                else:
                                    response_lines.append(f"<b>{source.name}</b>")
                                if source.content:
                                    response_lines.append(f"<blockquote>{source.content}</blockquote>")
                else:
                    response_lines.append(messages['fact_check']['no_info'])
        else:
            # Add claim with number only if there are multiple claims
            if total_claims > 1:
                response_lines.append(f"\n{idx}. <b>{claim.content}</b>")
            else:
                response_lines.append(f"\n<b>{claim.content}</b>")
            response_lines.append(messages['fact_check']['no_info'])

    response = "\n".join(response_lines)

    logger.info('Sending fact-check response', user_id=short_user_id, claims_count=len(processed_session.claims))
    await message.reply(response, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
