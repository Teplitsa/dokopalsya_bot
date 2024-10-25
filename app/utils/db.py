# from sqlalchemy.ext.asyncio import AsyncSession
# from tgbot.models.database_models import Request
# from utils.logging import setup_logger

#logger = get_logger(__name__)


# async def save_request_to_db(
#     session: AsyncSession, text_for_analysis: str, formatted_replies: list[str]
# ) -> None:
#     obj = Request(
#         user_input=text_for_analysis,
#         bot_response="\n".join(formatted_replies),
#     )

#     try:
#         session.add(obj)
#         await session.commit()
#         logger.debug("Request successfully saved to database.")
#     except Exception as e:
#         logger.error(f"Error saving request to database: {str(e)}")
#         await session.rollback()
