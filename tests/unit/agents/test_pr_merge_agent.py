"""TDD: PR Merge Agent tests"""

from agents.pr_merge_agent import (
    add_to_queue,
    handle_rebase,
    process_queue,
    validate_branch_protection,
)


class TestBranchProtectionChecks:
    """TDD: Branch Protection Checks"""

    def test_validate_branch_protection(self):
        """TDD: Validate branch protection"""
        # Arrange
        pr = {"checks": ["ci", "lint"], "status": "success"}

        # Act
        result = validate_branch_protection(pr)

        # Assert
        assert result is True


class TestMergeQueueManagement:
    """TDD: Merge Queue Management"""

    def test_add_pr_to_queue(self):
        """TDD: Add PR to queue"""
        # Arrange
        queue = []
        pr = {"id": 1}

        # Act
        queue = add_to_queue(queue, pr)

        # Assert
        assert len(queue) == 1

    def test_merge_next_pr(self):
        """TDD: Merge next PR"""
        # Arrange
        queue = [{"id": 1}, {"id": 2}]

        # Act
        merged, queue = process_queue(queue)

        # Assert
        assert merged["id"] == 1


class TestRebaseHandling:
    """TDD: Rebase Handling"""

    def test_rebase_required(self):
        """TDD: Rebase required"""
        # Arrange
        pr = {"behind": True}

        # Act
        result = handle_rebase(pr)

        # Assert
        assert result == "rebase"

    def test_rebase_not_required(self):
        """TDD: Rebase not required"""
        # Arrange
        pr = {"behind": False}

        # Act
        result = handle_rebase(pr)

        # Assert
        assert result == "noop"
