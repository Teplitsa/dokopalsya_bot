import asyncio

import aiojobs
import orjson
import structlog
import tenacity
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.utils.chat_action import ChatActionMiddleware
from aiohttp import web
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import close_all_sessions

from app import config, utils
from app.handlers.messages import router as messages_router
from app.middlewares.db_session import DataBaseSessionMiddleware
from app.middlewares.logging_middleware import StructLoggingMiddleware
from app.utils import prompt_utils
from app.utils.logging import get_logger
from app.web_handlers.tg_updates import tg_updates_app


async def create_db_connections(dp: Dispatcher) -> None:
    if not config.USE_POSTGRES:
        return

    logger: structlog.typing.FilteringBoundLogger = dp["business_logger"]

    logger.debug("Connecting to PostgreSQL")
    try:
        db_session_pool = await utils.connect_to_services.wait_postgres(
            logger=dp["db_logger"],
            database_url=config.SQLALCHEMY_DATABASE_URL,
        )
        dp["db_session_pool"] = db_session_pool
    except tenacity.RetryError:
        logger.error("Failed to connect to PostgreSQL after multiple retries")
        exit(1)

    if config.USE_CUSTOM_API_SERVER:
        dp["temp_bot_local_session"] = utils.smart_session.SmartAiogramAiohttpSession(
            api=TelegramAPIServer(
                base=config.CUSTOM_API_SERVER_BASE,
                file=config.CUSTOM_API_SERVER_FILE,
                is_local=config.CUSTOM_API_SERVER_IS_LOCAL,
            ),
            json_loads=orjson.loads,
            logger=dp["aiogram_session_logger"],
        )


async def close_db_connections(dp: Dispatcher) -> None:
    if "temp_bot_cloud_session" in dp.workflow_data:
        temp_bot_cloud_session: AiohttpSession = dp["temp_bot_cloud_session"]
        await temp_bot_cloud_session.close()
    if "temp_bot_local_session" in dp.workflow_data:
        temp_bot_local_session: AiohttpSession = dp["temp_bot_local_session"]
        await temp_bot_local_session.close()
    if config.USE_POSTGRES and "db_session_pool" in dp.workflow_data:
        await close_all_sessions()


async def setup_bot_main_menu(bot: Bot) -> None:
    main_menu_commands = [
        BotCommand(command="/info", description="Что я умею?"),
    ]

    await bot.set_my_commands(main_menu_commands)


def setup_handlers(dp: Dispatcher) -> None:
    dp.include_router(messages_router)


def setup_middlewares(dp: Dispatcher) -> None:
    dp.update.outer_middleware(StructLoggingMiddleware(logger=dp["aiogram_logger"]))
    if config.USE_POSTGRES:
        dp.update.middleware(DataBaseSessionMiddleware(session_pool=dp["db_session_pool"]))
    dp.message.middleware(ChatActionMiddleware())


def setup_logging(dp: Dispatcher) -> None:
    dp["aiogram_logger"] = get_logger("aiogram", "bot")
    dp["db_logger"] = get_logger("db", "database")
    dp["cache_logger"] = get_logger("cache", "caching")
    dp["app_logger"] = get_logger("app", "application")


async def setup_aiogram(dp: Dispatcher) -> None:
    setup_logging(dp)
    logger = dp["aiogram_logger"]
    logger.debug("Configuring aiogram")
    await create_db_connections(dp)
    setup_handlers(dp)
    setup_middlewares(dp)
    
    await load_prompts(dp)
    
    logger.info("Configured aiogram")


async def load_prompts(dp: Dispatcher) -> None:
    logger = dp["aiogram_logger"]
    logger.debug("Loading prompt templates")
    
    try:
        langfuse_client = prompt_utils.initialize_langfuse()
        loaded_prompts = prompt_utils.load_prompt_templates(langfuse_client)
        dp["loaded_prompts"] = loaded_prompts
        
        logger.info(f"Loaded {len(loaded_prompts)} prompt templates")
    except Exception as e:
        logger.error(f"Failed to load prompts: {str(e)}")
        # Instead of raising an error, we'll continue with an empty prompts dictionary
        dp["loaded_prompts"] = {}


async def aiohttp_on_startup(app: web.Application) -> None:
    dp: Dispatcher = app["dp"]
    workflow_data = {"app": app, "dispatcher": dp}
    if "bot" in app:
        workflow_data["bot"] = app["bot"]
    await dp.emit_startup(**workflow_data)


async def aiohttp_on_shutdown(app: web.Application) -> None:
    dp: Dispatcher = app["dp"]
    for i in [app, *app._subapps]:  # dirty
        if "scheduler" in i:
            scheduler: aiojobs.Scheduler = i["scheduler"]
            scheduler._closed = True
            while scheduler.pending_count != 0:
                dp["aiogram_logger"].info(
                    f"Waiting for {scheduler.pending_count} tasks to complete"
                )
                await asyncio.sleep(1)
    workflow_data = {"app": app, "dispatcher": dp}
    if "bot" in app:
        workflow_data["bot"] = app["bot"]
    await dp.emit_shutdown(**workflow_data)


async def aiogram_on_startup_webhook(dispatcher: Dispatcher, bot: Bot) -> None:
    await setup_aiogram(dispatcher)
    webhook_logger = dispatcher["aiogram_logger"].bind(webhook_url=config.MAIN_WEBHOOK_ADDRESS)
    webhook_logger.debug("Configuring webhook")
    await bot.set_webhook(
        url=config.MAIN_WEBHOOK_ADDRESS.format(
            token=config.BOT_TOKEN, bot_id=config.BOT_TOKEN.split(":")[0]
        ),
        allowed_updates=dispatcher.resolve_used_update_types(),
        secret_token=config.MAIN_WEBHOOK_SECRET_TOKEN,
    )
    webhook_logger.info("Configured webhook")
    await setup_bot_main_menu(bot)


async def aiogram_on_shutdown_webhook(dispatcher: Dispatcher, bot: Bot) -> None:
    dispatcher["aiogram_logger"].debug("Stopping webhook")
    await close_db_connections(dispatcher)
    await bot.session.close()
    dispatcher["aiogram_logger"].info("Stopped webhook")


async def aiogram_on_startup_polling(dispatcher: Dispatcher, bot: Bot) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await setup_aiogram(dispatcher)
    await setup_bot_main_menu(bot)
    dispatcher["aiogram_logger"].info("Started polling")


async def aiogram_on_shutdown_polling(dispatcher: Dispatcher, bot: Bot) -> None:
    dispatcher["aiogram_logger"].debug("Stopping polling")
    await close_db_connections(dispatcher)
    await bot.session.close()
    dispatcher["aiogram_logger"].info("Stopped polling")


async def setup_aiohttp_app(bot: Bot, dp: Dispatcher) -> web.Application:
    scheduler = aiojobs.Scheduler()
    app = web.Application()
     
    subapps: list[tuple[str, web.Application]] = [
        ("/tg/webhooks/", tg_updates_app),
    ]
    
    for prefix, subapp in subapps:
        subapp["bot"] = bot
        subapp["dp"] = dp
        subapp["scheduler"] = scheduler
        app.add_subapp(prefix, subapp)
    app["bot"] = bot
    app["dp"] = dp
    app["scheduler"] = scheduler
    app.on_startup.append(aiohttp_on_startup)
    app.on_shutdown.append(aiohttp_on_shutdown)
    return app


def run_migrations() -> None:
    if not config.USE_POSTGRES:
        return

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    migration_logger = get_logger(__name__, "migration")
    migration_logger.info("Migrations completed successfully")


def main() -> None:
    run_migrations()

    aiogram_session_logger = get_logger(__name__, "aiogram_session")

    if config.USE_CUSTOM_API_SERVER:
        session = utils.smart_session.SmartAiogramAiohttpSession(
            api=TelegramAPIServer(
                base=config.CUSTOM_API_SERVER_BASE,
                file=config.CUSTOM_API_SERVER_FILE,
                is_local=config.CUSTOM_API_SERVER_IS_LOCAL,
            ),
            json_loads=orjson.loads,
            logger=aiogram_session_logger,
        )
    else:
        session = utils.smart_session.SmartAiogramAiohttpSession(
            json_loads=orjson.loads,
            logger=aiogram_session_logger,
        )
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    dp = Dispatcher()

    dp["aiogram_session_logger"] = aiogram_session_logger

    if config.USE_WEBHOOK:
        dp.startup.register(aiogram_on_startup_webhook)
        dp.shutdown.register(aiogram_on_shutdown_webhook)
        web.run_app(
            asyncio.run(setup_aiohttp_app(bot, dp)),
            handle_signals=True,
            host=config.MAIN_WEBHOOK_LISTENING_HOST,
            port=config.MAIN_WEBHOOK_LISTENING_PORT,
        )
    else:
        dp.startup.register(aiogram_on_startup_polling)
        dp.shutdown.register(aiogram_on_shutdown_polling)
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
