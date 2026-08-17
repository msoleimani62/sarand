from sarand import utils


def test_utils_exports_expected_public_api() -> None:
    expected = {
        "default_output_name",
        "get_logger",
        "human_size",
        "is_binary",
        "make_command_result",
        "run_cmd",
        "run_cmd_async",
        "safe_relative",
        "setup_logging",
        "slugify_project_name",
        "summarize_tail",
    }

    assert set(utils.__all__) == expected


def test_utils_exports_are_available() -> None:
    for name in utils.__all__:
        assert hasattr(utils, name)


def test_utils_exports_match_declared_modules() -> None:
    from sarand.utils.command import (
        make_command_result,
        run_cmd,
        run_cmd_async,
        summarize_tail,
    )
    from sarand.utils.fs import (
        default_output_name,
        human_size,
        is_binary,
        safe_relative,
        slugify_project_name,
    )
    from sarand.utils.logging import get_logger, setup_logging

    expected = {
        "default_output_name": default_output_name,
        "get_logger": get_logger,
        "human_size": human_size,
        "is_binary": is_binary,
        "make_command_result": make_command_result,
        "run_cmd": run_cmd,
        "run_cmd_async": run_cmd_async,
        "safe_relative": safe_relative,
        "setup_logging": setup_logging,
        "slugify_project_name": slugify_project_name,
        "summarize_tail": summarize_tail,
    }

    for name, implementation in expected.items():
        assert getattr(utils, name) is implementation


def test_utils_all_contains_no_duplicates() -> None:
    assert len(utils.__all__) == len(set(utils.__all__))
