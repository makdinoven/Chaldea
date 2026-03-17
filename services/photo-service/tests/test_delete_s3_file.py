"""
Tests for delete_s3_file URL parsing and S3 key extraction.

Verifies that the function correctly extracts the S3 key from a full URL,
excluding the protocol, host, and bucket name segments.
"""

from unittest.mock import patch, MagicMock


# ===========================================================================
# delete_s3_file key extraction
# ===========================================================================

class TestDeleteS3FileKeyExtraction:
    """Verify that delete_s3_file extracts the correct S3 key from URL."""

    @patch("utils.s3_client")
    def test_backblaze_url_extracts_key_without_bucket(self, mock_s3):
        """
        URL: https://s3.eu-central-003.backblazeb2.com/fallofgods/subdir/file.webp
        Expected key: subdir/file.webp (not fallofgods/subdir/file.webp)
        """
        from utils import delete_s3_file

        delete_s3_file("https://s3.eu-central-003.backblazeb2.com/fallofgods/subdir/file.webp")

        mock_s3.delete_object.assert_called_once()
        call_kwargs = mock_s3.delete_object.call_args[1]
        assert call_kwargs["Key"] == "subdir/file.webp"

    @patch("utils.s3_client")
    def test_twc_url_extracts_key_without_bucket(self, mock_s3):
        """
        URL: https://s3.twcstorage.ru/mybucket/user_avatars/photo.webp
        Expected key: user_avatars/photo.webp
        """
        from utils import delete_s3_file

        delete_s3_file("https://s3.twcstorage.ru/mybucket/user_avatars/photo.webp")

        mock_s3.delete_object.assert_called_once()
        call_kwargs = mock_s3.delete_object.call_args[1]
        assert call_kwargs["Key"] == "user_avatars/photo.webp"

    @patch("utils.s3_client")
    def test_nested_subdirectory(self, mock_s3):
        """
        URL with multiple subdirectories.
        Expected key: a/b/c/file.webp
        """
        from utils import delete_s3_file

        delete_s3_file("https://s3.example.com/bucket/a/b/c/file.webp")

        call_kwargs = mock_s3.delete_object.call_args[1]
        assert call_kwargs["Key"] == "a/b/c/file.webp"

    @patch("utils.s3_client")
    def test_file_at_bucket_root(self, mock_s3):
        """
        URL with file directly in bucket root (no subdirectory).
        Expected key: file.webp
        """
        from utils import delete_s3_file

        delete_s3_file("https://s3.example.com/bucket/file.webp")

        call_kwargs = mock_s3.delete_object.call_args[1]
        assert call_kwargs["Key"] == "file.webp"

    @patch("utils.s3_client")
    def test_character_avatar_url(self, mock_s3):
        """
        Typical character avatar URL.
        Expected key: character_avatars/profile_photo_7_abc123.webp
        """
        from utils import delete_s3_file

        delete_s3_file("https://s3.eu-central-003.backblazeb2.com/fallofgods/character_avatars/profile_photo_7_abc123.webp")

        call_kwargs = mock_s3.delete_object.call_args[1]
        assert call_kwargs["Key"] == "character_avatars/profile_photo_7_abc123.webp"

    @patch("utils.s3_client")
    def test_s3_client_error_propagates(self, mock_s3):
        """If S3 client raises, delete_s3_file re-raises the exception."""
        from utils import delete_s3_file
        import pytest

        mock_s3.delete_object.side_effect = Exception("S3 error")

        with pytest.raises(Exception, match="S3 error"):
            delete_s3_file("https://s3.example.com/bucket/key.webp")
