import unittest

from workplace_thinker import WorkplaceInsightEngine

try:
    from fastapi.testclient import TestClient
    from workplace_thinker.api import app
except Exception:
    TestClient = None
    app = None


class WorkplaceInsightEngineTest(unittest.IsolatedAsyncioTestCase):
    async def test_builds_relationship_and_risk_graph(self):
        engine = WorkplaceInsightEngine()
        result = await engine.analyze(
            question="我是不是有背锅风险？",
            chat_messages=[
                {"role": "user", "content": "张伟说这个需求先做，不用审批，后面再补流程。"},
                {"role": "user", "content": "李娜提醒我，王强之前答应负责验收，但现在又改口说不是他负责。"},
                {"role": "user", "content": "张伟和王强私下沟通过，没有同步到项目群。"},
            ],
            org_chart=[
                {"name": "张伟", "title": "产品负责人", "team": "Product", "manager": "王强"},
                {"name": "王强", "title": "部门经理", "team": "Platform"},
                {"name": "李娜", "title": "资深同事", "team": "Product", "manager": "王强"},
            ],
        )

        self.assertGreaterEqual(result["meta"]["evidence_count"], 3)
        self.assertTrue(any(node["label"] == "张伟" for node in result["graph"]["nodes"]))
        self.assertTrue(any(edge["type"] in {"formal_reports_to", "collaborates_with", "commits_to"} for edge in result["graph"]["edges"]))
        categories = {risk["category"] for risk in result["risks"]}
        self.assertIn("process_bypass", categories)
        self.assertIn("information_asymmetry", categories)
        self.assertTrue(result["hidden_hypotheses"])
        self.assertTrue(all(h["status"] == "hypothesis_not_fact" for h in result["hidden_hypotheses"]))

    async def test_not_enough_evidence_is_safe(self):
        result = await WorkplaceInsightEngine().analyze(chat_messages=[], uploaded_texts=[], org_chart=[])
        self.assertEqual(0, result["meta"]["evidence_count"])
        self.assertIn("暂无", result["summary"])


class WorkplaceInsightAPITest(unittest.TestCase):
    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_api_analyze_endpoint(self):
        client = TestClient(app)
        response = client.post(
            "/api/v1/workplace/analyze",
            json={
                "question": "有什么隐藏风险？",
                "chat_messages": [{"role": "user", "content": "张伟说先做，不用审批，后补流程。"}],
                "org_chart": [{"name": "张伟", "title": "产品负责人"}],
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertIn("graph", payload)
        self.assertTrue(payload["risks"])

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_home_serves_graph_ui(self):
        client = TestClient(app)
        response = client.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("职场关系雷达", response.text)


if __name__ == "__main__":
    unittest.main()
