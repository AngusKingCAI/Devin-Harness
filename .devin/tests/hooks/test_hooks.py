"""Tests for hook scripts."""

import json
import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import pytest

# Add scripts to path
scripts_path = Path(__file__).parent.parent.parent / 'scripts'


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def workflow_state(temp_dir):
    """Create a workflow state file."""
    state_path = temp_dir / 'workflow-state.json'
    state = {
        'pipeline_id': 'test-pipeline',
        'pipeline_run_id': 'test-run-1',
        'status': 'running',
        'current_stage_id': 'stage1',
        'stage_states': {
            'stage1': {
                'status': 'running',
                'subagent': 'subagent_explore',
                'session_id': 'test-session-1',
                'started_at': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                'recovery_brief_needed': False,
                'human_approval_required': False
            }
        },
        'shared_context': {},
        'checkpoints': {}
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    return state_path


@pytest.fixture
def audit_log(temp_dir):
    """Create an audit log file."""
    audit_path = temp_dir / 'action-log.jsonl'
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    return audit_path


@pytest.fixture
def policy_file(temp_dir):
    """Create a policy file."""
    policy_path = temp_dir / 'policy.json'
    policy = {
        'destructive_commands': ['rm -rf', 'git push --force'],
        'always_allow_tools': ['read', 'grep'],
        'always_deny_tools': ['delete_database']
    }
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    with open(policy_path, 'w', encoding='utf-8') as f:
        json.dump(policy, f)
    return policy_path


@pytest.fixture
def decisions_db(temp_dir):
    """Create a decisions database."""
    db_path = temp_dir / 'decisions.sqlite'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def run_hook_script(hook_name, payload, env_vars, temp_dir):
    """Run a hook script as a subprocess."""
    hook_path = scripts_path / 'hooks' / f'{hook_name}.py'
    
    env = os.environ.copy()
    env.update(env_vars)
    
    result = subprocess.run(
        ['python', str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(temp_dir)
    )
    
    return result


class TestSessionStart:
    """Tests for SessionStart hook."""
    
    def test_session_start_with_recovery_brief(self, temp_dir, workflow_state, audit_log, decisions_db):
        """Test SessionStart hook with recovery brief needed."""
        # Update state to require recovery brief
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        state['stage_states']['stage1']['recovery_brief_needed'] = True
        with open(workflow_state, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_DECISIONS_DB_PATH': str(decisions_db),
            'ORCHESTRATOR_STAGE_ID': 'stage1'
        }
        
        # Simulate hook payload
        payload = {
            'session_id': 'test-session-1'
        }
        
        # Run hook
        result = run_hook_script('session_start', payload, env_vars, temp_dir)
        
        # Verify recovery brief flag was cleared
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert state['stage_states']['stage1']['recovery_brief_needed'] == False
        
        # Verify audit log was written
        assert audit_log.exists()
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0
        audit_entry = json.loads(lines[-1])
        assert audit_entry['hook_event'] == 'SessionStart'
    
    def test_session_start_without_recovery_brief(self, temp_dir, workflow_state, audit_log, decisions_db):
        """Test SessionStart hook without recovery brief needed."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_DECISIONS_DB_PATH': str(decisions_db),
            'ORCHESTRATOR_STAGE_ID': 'stage1'
        }
        
        # Simulate hook payload
        payload = {
            'session_id': 'test-session-1'
        }
        
        # Run hook
        result = run_hook_script('session_start', payload, env_vars, temp_dir)
        
        # Verify audit log was written
        assert audit_log.exists()
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0


class TestUserPromptSubmit:
    """Tests for UserPromptSubmit hook."""
    
    def test_user_prompt_submit_with_recovery_brief(self, temp_dir, workflow_state, audit_log, decisions_db):
        """Test UserPromptSubmit hook with recovery brief needed."""
        # Update state to require recovery brief
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        state['stage_states']['stage1']['recovery_brief_needed'] = True
        with open(workflow_state, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_DECISIONS_DB_PATH': str(decisions_db)
        }
        
        # Simulate hook payload
        payload = {
            'session_id': 'test-session-1',
            'prompt_id': 'prompt-1'
        }
        
        # Run hook
        result = run_hook_script('user_prompt_submit', payload, env_vars, temp_dir)
        
        # Verify recovery brief flag was cleared
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert state['stage_states']['stage1']['recovery_brief_needed'] == False


class TestPreToolUse:
    """Tests for PreToolUse hook."""
    
    def test_pre_tool_use_allow(self, temp_dir, workflow_state, audit_log, policy_file):
        """Test PreToolUse hook with allowed command."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_POLICY_PATH': str(policy_file)
        }
        
        # Simulate hook payload
        payload = {
            'tool_name': 'exec',
            'tool_input': {
                'command': 'echo "hello"'
            }
        }
        
        # Run hook
        result = run_hook_script('pre_tool_use', payload, env_vars, temp_dir)
        
        # Verify audit log was written
        assert audit_log.exists()
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0
        audit_entry = json.loads(lines[-1])
        assert audit_entry['hook_event'] == 'PreToolUse'
        assert audit_entry['payload']['decision'] == 'allow'
    
    def test_pre_tool_use_block_destructive(self, temp_dir, workflow_state, audit_log, policy_file):
        """Test PreToolUse hook blocking destructive command."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_POLICY_PATH': str(policy_file)
        }
        
        # Simulate hook payload with destructive command
        payload = {
            'tool_name': 'exec',
            'tool_input': {
                'command': 'rm -rf /important/data'
            }
        }
        
        # Run hook
        result = run_hook_script('pre_tool_use', payload, env_vars, temp_dir)
        
        # Exit code 2 for blocked commands
        assert result.returncode == 2
        
        # Verify audit log was written with block decision
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        audit_entry = json.loads(lines[-1])
        assert audit_entry['payload']['decision'] == 'block'


class TestPostToolUse:
    """Tests for PostToolUse hook."""
    
    def test_post_tool_use_heartbeat_update(self, temp_dir, workflow_state, audit_log, decisions_db):
        """Test PostToolUse hook updates heartbeat."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_DECISIONS_DB_PATH': str(decisions_db)
        }
        
        # Simulate hook payload
        payload = {
            'tool_name': 'read',
            'tool_input': {
                'file_path': 'test.txt'
            },
            'tool_response': {
                'success': True,
                'content': 'test content'
            }
        }
        
        # Run hook
        result = run_hook_script('post_tool_use', payload, env_vars, temp_dir)
        
        # Verify heartbeat was updated
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert 'heartbeat' in state['stage_states']['stage1']
        assert 'last_beat_at' in state['stage_states']['stage1']['heartbeat']
    
    def test_post_tool_use_failed_response(self, temp_dir, workflow_state, audit_log, decisions_db):
        """Test PostToolUse hook with failed tool response."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_DECISIONS_DB_PATH': str(decisions_db)
        }
        
        # Simulate hook payload with failed response
        payload = {
            'tool_name': 'exec',
            'tool_input': {
                'command': 'invalid_command'
            },
            'tool_response': {
                'success': False,
                'error': 'Command not found'
            }
        }
        
        # Run hook
        result = run_hook_script('post_tool_use', payload, env_vars, temp_dir)
        
        # Verify audit log was written
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0


class TestPermissionRequest:
    """Tests for PermissionRequest hook."""
    
    def test_permission_request_always_allow(self, temp_dir, workflow_state, audit_log, policy_file):
        """Test PermissionRequest hook with always-allow tool."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_POLICY_PATH': str(policy_file)
        }
        
        # Simulate hook payload
        payload = {
            'tool_name': 'read'
        }
        
        # Run hook
        result = run_hook_script('permission_request', payload, env_vars, temp_dir)
        
        # Verify audit log was written
        assert audit_log.exists()
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0
        audit_entry = json.loads(lines[-1])
        assert audit_entry['payload']['decision'] == 'approve'
    
    def test_permission_request_always_deny(self, temp_dir, workflow_state, audit_log, policy_file):
        """Test PermissionRequest hook with always-deny tool."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log),
            'ORCHESTRATOR_POLICY_PATH': str(policy_file)
        }
        
        # Simulate hook payload
        payload = {
            'tool_name': 'delete_database'
        }
        
        # Run hook
        result = run_hook_script('permission_request', payload, env_vars, temp_dir)
        
        # Verify audit log was written with block decision
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        audit_entry = json.loads(lines[-1])
        assert audit_entry['payload']['decision'] == 'block'


class TestStop:
    """Tests for Stop hook."""
    
    def test_stop_hook(self, temp_dir, workflow_state, audit_log):
        """Test Stop hook marks stage as stopped."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log)
        }
        
        # Simulate hook payload
        payload = {
            'stop_reason': 'user_interrupted'
        }
        
        # Run hook
        result = run_hook_script('stop', payload, env_vars, temp_dir)
        
        # Verify stage was marked as stopped
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert state['stage_states']['stage1']['status'] == 'stopped'
        assert state['stage_states']['stage1']['stop_reason'] == 'user_interrupted'
        
        # Verify audit log was written
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0
        audit_entry = json.loads(lines[-1])
        assert audit_entry['hook_event'] == 'Stop'


class TestPostCompaction:
    """Tests for PostCompaction hook."""
    
    def test_post_compaction_heartbeat_update(self, temp_dir, workflow_state, audit_log):
        """Test PostCompaction hook updates heartbeat."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log)
        }
        
        # Simulate hook payload
        payload = {
            'session_id': 'test-session-1'
        }
        
        # Run hook
        result = run_hook_script('post_compaction', payload, env_vars, temp_dir)
        
        # Verify heartbeat was updated
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert 'heartbeat' in state['stage_states']['stage1']
        assert 'last_compaction_at' in state['stage_states']['stage1']['heartbeat']


class TestSessionEnd:
    """Tests for SessionEnd hook."""
    
    def test_session_end_completed(self, temp_dir, workflow_state, audit_log):
        """Test SessionEnd hook with completed session."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log)
        }
        
        # Simulate hook payload
        payload = {
            'session_id': 'test-session-1',
            'end_reason': 'completed'
        }
        
        # Run hook
        result = run_hook_script('session_end', payload, env_vars, temp_dir)
        
        # Verify stage was marked as completed
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert state['stage_states']['stage1']['status'] == 'completed'
        assert 'completed_at' in state['stage_states']['stage1']
        
        # Verify audit log was written
        with open(audit_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) > 0
        audit_entry = json.loads(lines[-1])
        assert audit_entry['hook_event'] == 'SessionEnd'
    
    def test_session_end_stopped(self, temp_dir, workflow_state, audit_log):
        """Test SessionEnd hook with stopped session."""
        # Set environment variables
        env_vars = {
            'ORCHESTRATOR_PROJECT_ROOT': str(temp_dir),
            'ORCHESTRATOR_STATE_PATH': str(workflow_state),
            'ORCHESTRATOR_AUDIT_LOG_PATH': str(audit_log)
        }
        
        # Simulate hook payload
        payload = {
            'session_id': 'test-session-1',
            'end_reason': 'error'
        }
        
        # Run hook
        result = run_hook_script('session_end', payload, env_vars, temp_dir)
        
        # Verify stage was marked as stopped
        with open(workflow_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        assert state['stage_states']['stage1']['status'] == 'stopped'
        assert state['stage_states']['stage1']['stop_reason'] == 'error'