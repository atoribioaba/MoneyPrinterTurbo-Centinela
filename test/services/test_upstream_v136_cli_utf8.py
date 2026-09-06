from unittest.mock import Mock, patch

import cli


def test_force_utf8_console_reconfigures_stdout_and_stderr():
    stdout = Mock()
    stderr = Mock()

    with patch.object(cli.sys, "stdout", stdout), patch.object(cli.sys, "stderr", stderr):
        cli._force_utf8_console()

    stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
    stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")


def test_force_utf8_console_tolerates_unreconfigurable_stream():
    stream = Mock()
    stream.reconfigure.side_effect = ValueError("stream already detached")

    with patch.object(cli.sys, "stdout", stream), patch.object(cli.sys, "stderr", stream):
        cli._force_utf8_console()
