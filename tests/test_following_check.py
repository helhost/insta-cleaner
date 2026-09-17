import json
import unittest

from tools.following_check import FollowingTracker, following_request


def body(pk="1", more=True, cursor="next", **extra):
    return json.dumps(
        dict(
            users=[{"pk": pk, "username": "example"}],
            status="ok",
            has_more=more,
            next_max_id=cursor,
            should_limit_list_of_followings=False,
            hidden_following_account_count=0,
            **extra
        )
    )


class FollowingTests(unittest.TestCase):
    def test_username_change_does_not_change_membership(self):
        t = FollowingTracker()
        t.add(("42", "", True), 200, body("1", False, ""))
        renamed = json.loads(body("1", False, ""))
        renamed["users"][0]["username"] = "renamed"
        self.assertTrue(t.add(("42", "", True), 200, json.dumps(renamed))["complete"])

    def test_failure_reasons_exclude_raw_response(self):
        t = FollowingTracker()
        result = t.add(("42", "", True), 200, "PRIVATE_SECRET")
        self.assertEqual(
            result["reasons"], ["invalid JSON or response body unavailable"]
        )
        result = t.add(("42", "", True), 429, "")
        self.assertIn("HTTP 429", result["reasons"])

    def test_changed_members_still_fail(self):
        t = FollowingTracker()
        t.add(("42", "", True), 200, body("1", False, ""))
        self.assertFalse(t.add(("42", "", True), 200, body("2", False, ""))["complete"])

    def test_chain_and_count(self):
        t = FollowingTracker()
        t.profile_counts('{"data":{"id":"42","following_count":2}}')
        self.assertFalse(t.add(("42", "", True), 200, body())["complete"])
        self.assertTrue(
            t.add(("42", "next", True), 200, body("2", False, ""))["complete"]
        )
        t.expected["42"] = 3
        self.assertFalse(t.summary("42")["complete"])

    def test_out_of_order_and_duplicates(self):
        t = FollowingTracker()
        t.add(("42", "next", True), 200, body("2", False, ""))
        self.assertFalse(t.summary("42")["complete"])
        t.add(("42", "", True), 200, body())
        self.assertTrue(t.summary("42")["complete"])
        t.add(("42", "", True), 200, body())
        self.assertEqual(t.summary("42")["users"], 2)

    def test_bad_page_and_account_separation(self):
        t = FollowingTracker()
        t.add(("42", "", True), 429, "")
        t.add(("43", "", True), 200, body("2", False, ""))
        self.assertFalse(t.summary("42")["complete"])
        self.assertTrue(t.summary("43")["complete"])

    def test_restrictions_and_missing_terminal(self):
        for changes in (
            {"has_more": None},
            {"should_limit_list_of_followings": True},
            {"hidden_following_account_count": 1},
        ):
            data = json.loads(body("1", False, ""))
            data.update(changes)
            t = FollowingTracker()
            self.assertFalse(t.add(("42", "", True), 200, json.dumps(data))["complete"])

    def test_scope(self):
        url = "https://www.instagram.com/api/v1/friendships/42/following/"
        self.assertEqual(following_request(url + "?count=12"), ("42", "", True))
        self.assertEqual(following_request(url + "?query=someone")[2], False)
        self.assertIsNone(following_request(url.replace("instagram.com", "evil.test")))
