"""Run external device commands without invoking a shell.

The synchronous interface lets Flask services capture process output safely.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass


class ProcessTimeoutError(TimeoutError):
    """Report that an external device command exceeded its time limit."""


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Store a command's exit status and captured text output.

    Attributes:
        return_code: Exit status returned by the external command.
        stdout: Standard output decoded as UTF-8.
        stderr: Standard error decoded as UTF-8.
    """

    return_code: int
    stdout: str
    stderr: str


def run_process(
    executable: str,
    arguments: Sequence[str],
    timeout_seconds: float,
) -> ProcessResult:
    """Run one executable with separate arguments and captured output.

    Args:
        executable: Absolute path to the command to execute.
        arguments: Command arguments passed without shell interpretation.
        timeout_seconds: Maximum time allowed for command completion.

    Returns:
        Exit status, standard output, and standard error from the command.

    Raises:
        FileNotFoundError: If the executable cannot be found.
        OSError: If the operating system cannot start the process.
        ProcessTimeoutError: If the command exceeds its time limit.
        RuntimeError: If process output or its exit status is unavailable.
    """
    return asyncio.run(_run_process(executable, arguments, timeout_seconds))


async def _run_process(
    executable: str,
    arguments: Sequence[str],
    timeout_seconds: float,
) -> ProcessResult:
    """Run and collect one process in an asyncio event loop.

    Args:
        executable: Absolute path to the command to execute.
        arguments: Command arguments passed without shell interpretation.
        timeout_seconds: Maximum time allowed for command completion.

    Returns:
        Exit status, standard output, and standard error from the command.

    Raises:
        FileNotFoundError: If the executable cannot be found.
        OSError: If the operating system cannot start the process.
        ProcessTimeoutError: If the command exceeds its time limit.
        RuntimeError: If process output or its exit status is unavailable.
    """
    process = await asyncio.create_subprocess_exec(
        executable,
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError as err:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError as kill_error:
                await process.communicate()
                raise ProcessTimeoutError from kill_error
        await process.communicate()
        raise ProcessTimeoutError from err

    return_code = process.returncode
    if return_code is None:
        raise RuntimeError
    return ProcessResult(
        return_code=return_code,
        stdout=stdout_data.decode("utf-8", errors="replace"),
        stderr=stderr_data.decode("utf-8", errors="replace"),
    )
