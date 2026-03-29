"""Tests for authentication utilities"""

from website.auth import hash_password, verify_password


class TestAuthFunctions:
    """Test password hashing and verification functions"""

    def test_hash_password_creates_hash(self):
        """Test password hashing creates non-plain output"""
        password = "test_password_123"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 20  # bcrypt hashes are long

    def test_hash_password_is_string(self):
        """Test hash_password returns string"""
        hashed = hash_password("test_password")
        assert isinstance(hashed, str)

    def test_verify_password_success(self):
        """Test correct password verification"""
        password = "correct_password"
        hashed = hash_password(password)

        result = verify_password(password, hashed)
        assert result is True

    def test_verify_password_failure(self):
        """Test incorrect password verification"""
        password = "correct_password"
        hashed = hash_password(password)

        result = verify_password("wrong_password", hashed)
        assert result is False

    def test_verify_password_empty_string(self):
        """Test verification with empty password"""
        hashed = hash_password("test")
        result = verify_password("", hashed)
        assert result is False

    def test_hash_same_password_different_hashes(self):
        """Test same password produces different hashes (due to salt)"""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Different hashes due to random salt in bcrypt
        assert hash1 != hash2
