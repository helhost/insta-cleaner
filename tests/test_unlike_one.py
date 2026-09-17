import unittest
from tools.unlike_one import selected_item, require_same_account


class UnlikeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.item = dict(
            code="ABC",
            product="clips",
            relationship="not-followed",
            evidence="matched",
            media_id="100",
            author_id="42",
        )

    def test_exact_single_selection(self):
        self.assertEqual(selected_item({"selected": [self.item]}, "ABC"), self.item)
        for rows in [[], [self.item, self.item]]:
            with self.assertRaises(ValueError):
                selected_item({"selected": rows}, "ABC")

    def test_unresolved_or_wrong_content_rejected(self):
        for changes in [
            {"evidence": "inferred"},
            {"relationship": "followed"},
            {"product": "feed"},
            {"author_id": None},
        ]:
            with self.assertRaises(ValueError):
                selected_item({"selected": [{**self.item, **changes}]}, "ABC")

    def test_wrong_account_rejected(self):
        require_same_account("1", "1")
        for expected, actual in [("1", "2"), (None, None)]:
            with self.assertRaises(ValueError):
                require_same_account(expected, actual)


class SingleClickTests(unittest.IsolatedAsyncioTestCase):
    async def test_click_once_and_reload_verify(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        from tools.unlike_one import click_and_verify

        unlike = SimpleNamespace(click=AsyncMock())
        like = SimpleNamespace(wait_for=AsyncMock())
        remaining = SimpleNamespace(count=AsyncMock(return_value=0))
        actions = SimpleNamespace(locator=Mock(side_effect=[like, remaining]))
        page = SimpleNamespace(
            reload=AsyncMock(), url="https://www.instagram.com/p/ABC/"
        )
        with patch("tools.unlike_one.post_actions", AsyncMock(return_value=actions)):
            await click_and_verify(page, unlike, like, "ABC")
        unlike.click.assert_awaited_once()
        page.reload.assert_awaited_once()

    async def test_uncertain_click_never_retried(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from tools.unlike_one import click_and_verify

        unlike = SimpleNamespace(click=AsyncMock(side_effect=TimeoutError()))
        page = SimpleNamespace(reload=AsyncMock())
        with self.assertRaises(TimeoutError):
            await click_and_verify(page, unlike, None, "ABC")
        unlike.click.assert_awaited_once()
        page.reload.assert_not_awaited()
