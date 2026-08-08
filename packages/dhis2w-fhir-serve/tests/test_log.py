"""The access log: one line per interaction, and the configuration the server process runs under."""

from __future__ import annotations

import logging
import sys

import httpx
import pytest
from dhis2w_fhir_serve.log import LOGGER_NAME, configure_logging


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == LOGGER_NAME]


async def test_a_served_request_logs_one_line(client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await client.get("/Questionnaire?_id=d2-pr-anc-visit-q")

    lines = [line for line in _messages(caplog) if line.startswith("GET /Questionnaire")]
    assert len(lines) == 1
    assert lines[0].startswith("GET /Questionnaire?_id=d2-pr-anc-visit-q -> 200 ")
    assert lines[0].endswith("ms")


async def test_a_refused_request_logs_its_status(client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await client.get("/Patient/anything")

    assert any(line.startswith("GET /Patient/anything -> 404 ") for line in _messages(caplog))


def test_configure_logging_sends_this_package_to_stderr() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    handlers, level, propagate = logger.handlers, logger.level, logger.propagate
    try:
        configure_logging()

        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stderr
        assert logger.level == logging.INFO
        assert logger.propagate is False
    finally:
        logger.handlers, logger.level, logger.propagate = handlers, level, propagate
