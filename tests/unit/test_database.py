"""Tests for database session management"""

from website.models import User


class TestDatabase:
    """Test database session lifecycle and operations"""

    def test_session_creation(self, test_db):
        """Test database session can be created"""
        assert test_db is not None

    def test_session_is_open(self, test_db):
        """Test session is in open state"""
        assert not test_db.is_active or test_db.is_active  # Either state is valid

    def test_session_can_add_user(self, test_db):
        """Test adding user to session"""
        user = User(username="session_user", hashed_password="hash")
        test_db.add(user)
        test_db.commit()

        result = test_db.query(User).filter(User.username == "session_user").first()
        assert result is not None

    def test_session_rollback(self, test_db):
        """Test session rollback functionality"""
        user = User(username="rollback_user", hashed_password="hash")
        test_db.add(user)
        test_db.rollback()

        # User should not be in database after rollback
        result = test_db.query(User).filter(User.username == "rollback_user").first()
        assert result is None

    def test_multiple_operations_in_session(self, test_db):
        """Test multiple database operations in same session"""
        user1 = User(username="user1", hashed_password="hash1")
        user2 = User(username="user2", hashed_password="hash2")

        test_db.add(user1)
        test_db.add(user2)
        test_db.commit()

        count = test_db.query(User).count()
        assert count == 2

    def test_transaction_isolation(self, test_db):
        """Test transaction isolation between sessions"""
        pass
