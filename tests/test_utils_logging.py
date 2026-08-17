import logging

from sarand.utils.logging import get_logger, setup_logging


def test_get_logger_returns_root_sarand_logger() -> None:
    logger = get_logger()

    assert logger.name == "sarand"


def test_get_logger_returns_child_logger() -> None:
    logger = get_logger("cache")

    assert logger.name == "sarand.cache"


def test_get_logger_child_names_are_namespaced() -> None:
    logger = get_logger("analyzer.python")

    assert logger.name == "sarand.analyzer.python"
    assert logger.name.startswith("sarand.")


def test_setup_logging_defaults_to_warning() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()
        setup_logging()

        assert logger.level == logging.WARNING
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_setup_logging_verbose_uses_info() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()
        setup_logging(verbose=True)

        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_setup_logging_debug_uses_debug() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()
        setup_logging(debug=True)

        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_setup_logging_debug_takes_precedence_over_verbose() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()
        setup_logging(verbose=True, debug=True)

        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_setup_logging_does_not_duplicate_handlers() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()

        setup_logging()
        first_handlers = list(logger.handlers)

        setup_logging(verbose=True)
        second_handlers = list(logger.handlers)

        setup_logging(debug=True)
        third_handlers = list(logger.handlers)

        assert len(first_handlers) == 1
        assert second_handlers == first_handlers
        assert third_handlers == first_handlers
        assert logger.level == logging.DEBUG
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_setup_logging_updates_existing_handler_level_configuration() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()

        setup_logging()
        handler = logger.handlers[0]

        assert handler.level == logging.NOTSET
        assert handler.formatter is not None
        assert handler.formatter.datefmt == "%H:%M:%S"
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_setup_logging_uses_expected_formatter() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()
        setup_logging()

        handler = logger.handlers[0]
        formatter = handler.formatter

        assert formatter is not None
        assert formatter._fmt == ("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        assert formatter.datefmt == "%H:%M:%S"
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)


def test_child_logger_inherits_sarand_configuration() -> None:
    logger = get_logger()
    original_handlers = list(logger.handlers)

    try:
        logger.handlers.clear()
        setup_logging(debug=True)

        child = get_logger("cache")

        assert child.parent is logger
        assert child.level == logging.NOTSET
        assert logger.level == logging.DEBUG
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
