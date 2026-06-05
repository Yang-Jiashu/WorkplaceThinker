import unittest

from workplace_thinker import WorkplaceInsightEngine, WorkplaceInsightHarness

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
        self.assertTrue(any(node["type"] == "risk_signal" for node in result["graph"]["nodes"]))


class WorkplaceInsightHarnessTest(unittest.IsolatedAsyncioTestCase):
    async def test_harness_wraps_one_box_input_with_controls(self):
        result = await WorkplaceInsightHarness().analyze_information(
            """
            组织架构：张伟 - 产品负责人 - Product 团队 - 汇报王强
            张伟说这个需求先做，不用审批，后面再补流程。
            张伟和王强私下沟通过，没有同步到项目群。
            """,
            question="有什么隐藏风险？",
        )
        self.assertEqual("Workplace Insight Harness", result["harness"]["name"])
        self.assertIn("graph_harness", result["harness"]["layers"])
        self.assertIn("control_harness", result["harness"]["layers"])
        self.assertEqual("raw_information", result["meta"]["input_mode"])
        self.assertTrue(result["graph_view"]["legend"])
        self.assertGreaterEqual(result["graph_view"]["high_risk_count"], 1)
        self.assertFalse(result["control_manifest"]["memory_policy"]["persist_unconfirmed_hypotheses"])
        self.assertTrue(result["control_manifest"]["actions"])
        self.assertTrue(any(node["type"] == "hidden_hypothesis" for node in result["graph"]["nodes"]))
        self.assertTrue(any(edge["type"] in {"formal_reports_to", "collaborates_with", "commits_to"} for edge in result["graph"]["edges"]))
        self.assertTrue(any(edge["type"] == "mentions_risk" for edge in result["graph"]["edges"]))
        categories = {risk["category"] for risk in result["risks"]}
        self.assertIn("process_bypass", categories)
        self.assertIn("information_asymmetry", categories)
        self.assertTrue(result["hidden_hypotheses"])
        self.assertTrue(all(h["status"] == "hypothesis_not_fact" for h in result["hidden_hypotheses"]))

    async def test_not_enough_evidence_is_safe(self):
        result = await WorkplaceInsightEngine().analyze(chat_messages=[], uploaded_texts=[], org_chart=[])
        self.assertEqual(0, result["meta"]["evidence_count"])
        self.assertIn("暂无", result["summary"])

    async def test_raw_information_requires_only_one_input(self):
        result = await WorkplaceInsightEngine().analyze_information(
            """
            问题：我是不是有背锅风险？
            组织架构：张伟 - 产品负责人 - Product 团队 - 汇报王强
            组织架构：王强 - 部门经理 - Platform 团队
            组织架构：李娜 - 资深同事 - Product 团队 - 汇报王强

            张伟说这个需求先做，不用审批，后面再补流程。
            李娜提醒我，王强之前答应负责验收，但现在又改口说不是他负责。
            张伟和王强私下沟通过，没有同步到项目群。
            """
        )
        labels = {node["label"] for node in result["people"]}
        self.assertIn("张伟", labels)
        self.assertIn("王强", labels)
        self.assertEqual("raw_information", result["meta"]["input_mode"])
        self.assertTrue(result["risks"])
        self.assertTrue(any(node["type"] == "risk_signal" for node in result["graph"]["nodes"]))


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
        self.assertIn("harness", payload)

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_api_raw_analyze_endpoint(self):
        client = TestClient(app)
        response = client.post(
            "/api/v1/workplace/analyze/raw",
            json={
                "information": "组织架构：张伟 - 产品负责人 - 汇报王强\n张伟说先做，不用审批，后补流程。",
                "question": "有什么风险？",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("raw_information", payload["meta"]["input_mode"])
        self.assertTrue(payload["risks"])
        self.assertIn("control_manifest", payload)

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_home_serves_graph_ui(self):
        client = TestClient(app)
        response = client.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("职场关系雷达", response.text)


if __name__ == "__main__":
    unittest.main()
