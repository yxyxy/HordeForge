import json
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from cli.llm_cli import LlmCli


class TestLlmCli:
    def setup_method(self):
        self.cli = LlmCli()

    def test_load_save_settings(self):
        """Test loading and saving settings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock expanduser to use temp directory
            with patch("os.path.expanduser") as mock_expanduser:
                # Create the temporary settings file path
                temp_settings_file = os.path.join(temp_dir, "llm_settings.json")
                temp_profiles_dir = os.path.join(temp_dir, "profiles")
                os.makedirs(temp_profiles_dir, exist_ok=True)

                # Configure mock to return temp paths
                def mock_expanduser_side_effect(path):
                    if path.startswith("~/.hordeforge/profiles"):
                        return os.path.join(
                            temp_dir,
                            "profiles",
                            path.split("/")[-1] if "/" in path else "default.json",
                        )
                    elif path == "~/.hordeforge/llm_settings.json":
                        return temp_settings_file
                    elif path == "~/.hordeforge":
                        return temp_dir
                    else:
                        return path.replace("~/.hordeforge", temp_dir)

                mock_expanduser.side_effect = mock_expanduser_side_effect

                settings = {"provider": "openai", "model": "gpt-4"}

                # Test save
                self.cli.save_settings(settings)

                # Test load
                loaded_settings = self.cli.load_settings()
                assert loaded_settings == settings

    def test_list_profiles(self):
        """Test listing profiles."""
        with tempfile.TemporaryDirectory() as temp_dir:
            profiles_dir = os.path.join(temp_dir, "profiles")
            os.makedirs(profiles_dir)

            with patch(
                "os.path.expanduser", side_effect=lambda x: x.replace("~/.hordeforge", temp_dir)
            ):
                # Create some test profile files
                with open(os.path.join(profiles_dir, "test1.json"), "w") as f:
                    json.dump({}, f)
                with open(os.path.join(profiles_dir, "test2.json"), "w") as f:
                    json.dump({}, f)

                profiles = self.cli.list_profiles()
                assert "default" in profiles
                assert "test1" in profiles
                assert "test2" in profiles

    def test_delete_profile(self):
        """Test deleting a profile."""
        with tempfile.TemporaryDirectory() as temp_dir:
            profiles_dir = os.path.join(temp_dir, "profiles")
            os.makedirs(profiles_dir)

            # Create a test profile
            test_profile = os.path.join(profiles_dir, "test_profile.json")
            with open(test_profile, "w") as f:
                json.dump({"provider": "openai"}, f)

            with patch(
                "os.path.expanduser", side_effect=lambda x: x.replace("~/.hordeforge", temp_dir)
            ):
                # Test deleting non-default profile
                result = self.cli.delete_profile("test_profile")
                assert result is True
                assert not os.path.exists(test_profile)

                # Test trying to delete default profile (should fail)
                result = self.cli.delete_profile("default")
                assert result is False

    @pytest.mark.asyncio
    async def test_process_prompt(self):
        """Test processing a prompt."""
        # Mock the API
        mock_api = Mock()
        mock_api.config.provider.value = "openai"
        mock_api.config.model = "gpt-4"

        # Import the real chunk classes to create proper mocks
        from agents.llm_wrapper import ApiStreamTextChunk, ApiStreamUsageChunk

        # Mock the create_message method to yield test chunks
        async def mock_create_message(system_prompt, messages):
            # Yield text chunk
            text_chunk = ApiStreamTextChunk(text="Test response")
            yield text_chunk
            # Yield usage chunk
            usage_chunk = ApiStreamUsageChunk(input_tokens=10, output_tokens=20)
            yield usage_chunk

        mock_api.create_message = mock_create_message

        # Capture print output
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            await self.cli.process_prompt(mock_api, "Test system", "Test prompt")
            output = captured_output.getvalue()
            assert "Test response" in output
            assert "Input=10, Output=20" in output
        finally:
            sys.stdout = sys.__stdout__

    @pytest.mark.asyncio
    async def test_test_provider(self):
        """Test provider connectivity test."""
        # Mock the API
        mock_api = Mock()
        mock_api.config.provider.value = "openai"
        mock_api.config.model = "gpt-4"

        # Mock the create_message method
        async def mock_create_message(system_prompt, messages):
            yield Mock(spec_set=["text"], text="Hello world")
            yield Mock(spec_set=["input_tokens", "output_tokens"], input_tokens=5, output_tokens=10)

        mock_api.create_message = mock_create_message

        # Capture print output
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            await self.cli.test_provider(mock_api)
            output = captured_output.getvalue()
            assert "Testing openai" in output
            assert "Success!" in output
        finally:
            sys.stdout = sys.__stdout__

    def test_get_default_model(self):
        """Test getting default models for providers."""
        from agents.llm_api import ApiProvider

        # Test a few providers
        assert self.cli._get_default_model(ApiProvider.OPENAI) == "gpt-4o"
        assert self.cli._get_default_model(ApiProvider.ANTHROPIC) == "claude-sonnet-4-20250514"
        assert self.cli._get_default_model(ApiProvider.OLLAMA) == "llama2"

    @pytest.mark.asyncio
    async def test_chat_interactive(self):
        """Test interactive chat mode."""
        # This is a complex test that would require mocking input/output
        # For now, we'll just test that the method exists and can be called
        mock_api = Mock()
        mock_api.config.provider.value = "openai"
        mock_api.config.model = "gpt-4"

        # Mock the create_message method
        async def mock_create_message(system_prompt, messages):
            yield Mock(spec_set=["text"], text="Hello!")

        mock_api.create_message = mock_create_message

        # Mock input to simulate user interaction
        with patch("builtins.input", side_effect=["test message", "quit"]):
            with patch("builtins.print"):  # Suppress print output
                await self.cli.chat_interactive(mock_api, "Test system")


def test_cli_parser():
    """Test CLI argument parser setup."""
    cli = LlmCli()
    parser = cli.setup_parser()

    # Test that parser has expected arguments
    args = parser.parse_args(["--provider", "openai", "--model", "gpt-4", "chat"])
    assert args.provider == "openai"
    assert args.model == "gpt-4"
    assert args.command == "chat"

    # Test plan subcommand
    args = parser.parse_args(["plan", "test", "prompt"])
    assert args.command == "plan"
    assert args.prompt == ["test", "prompt"]

    # Test act subcommand
    args = parser.parse_args(["act", "test", "prompt"])
    assert args.command == "act"
    assert args.prompt == ["test", "prompt"]

    # Test global plan flag (when no subcommand is provided)
    args = parser.parse_args(["--plan"])
    assert args.plan is True
    assert args.command is None

    # Test global act flag (when no subcommand is provided)
    args = parser.parse_args(["--act"])
    assert args.act is True
    assert args.command is None

    # Test settings mode
    args = parser.parse_args(["--settings"])
    assert args.settings is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
