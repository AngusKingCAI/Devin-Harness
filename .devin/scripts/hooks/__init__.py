"""Hook scripts for Devin CLI Orchestrator."""

from .session_start import main as session_start_main
from .user_prompt_submit import main as user_prompt_submit_main
from .pre_tool_use import main as pre_tool_use_main
from .post_tool_use import main as post_tool_use_main
from .permission_request import main as permission_request_main
from .stop import main as stop_main
from .post_compaction import main as post_compaction_main
from .session_end import main as session_end_main

__all__ = [
    'session_start_main',
    'user_prompt_submit_main',
    'pre_tool_use_main',
    'post_tool_use_main',
    'permission_request_main',
    'stop_main',
    'post_compaction_main',
    'session_end_main',
]