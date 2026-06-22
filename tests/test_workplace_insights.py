import unittest

from workplace_thinker import (
    CURRENT_MEMORY_SCHEMA_VERSION,
    ModelConfigManager,
    ModelRouter,
    OrgStructureImporter,
    ProviderConfig,
    WorkplaceInsightEngine,
    WorkplaceInsightHarness,
    WorkplaceMemoryMigrator,
)

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
        self.assertIn("work_graph", result)
        self.assertIn("org_structure", result)
        self.assertEqual(2, result["org_structure"]["summary"]["department_count"])
        self.assertGreaterEqual(result["org_structure"]["summary"]["reporting_line_count"], 2)
        self.assertIn("knowledge_context", result)
        self.assertTrue(any(node["type"] == "work_object" for node in result["graph"]["nodes"]))


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
        self.assertIn("org_structure", result)
        self.assertTrue(result["org_structure"]["reporting_tree"])
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
        self.assertTrue(result["knowledge_context"]["active_frames"])
        self.assertTrue(result["behavior_observations"])
        self.assertTrue(all(o["status"] == "observable_pattern_not_personality" for o in result["behavior_observations"]))
        self.assertIn("evidence_event_summary", result)
        self.assertGreaterEqual(result["evidence_event_summary"]["total"], 1)
        self.assertIn("person_histories", result)
        self.assertIn("张伟", result["person_histories"])
        zhang_history = result["person_histories"]["张伟"]
        self.assertIn("不是人格定性", zhang_history["safety_note"])
        self.assertTrue(zhang_history["current"]["risks"])
        self.assertTrue(zhang_history["current"]["evidence"])

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

    async def test_work_and_knowledge_networks_are_injected(self):
        result = await WorkplaceInsightEngine().analyze_information(
            """
            组织架构：张伟 - 产品负责人 - Product 团队 - 汇报王强
            李娜提醒我，王强之前答应负责验收，但现在又改口说不是他负责。
            张伟说这个需求周五必须上线，先不用审批，验收后面再补，大家先对齐口径。
            王强说张伟负责方案，我负责文档和上线检查，后面我来闭环。
            张伟和王强私下沟通，说老板已经点头，先别在群里公开。
            """,
            question="工作内容和关系怎么拆？",
        )
        labels = {node["label"] for node in result["people"]}
        self.assertIn("李娜", labels)
        self.assertNotIn("王强之前", labels)
        self.assertNotIn("周五上线", labels)
        self.assertGreaterEqual(result["meta"]["work_object_count"], 1)
        self.assertGreaterEqual(result["meta"]["knowledge_frame_count"], 1)
        self.assertTrue(result["work_graph"]["nodes"])
        self.assertTrue(result["work_graph"]["edges"])
        self.assertGreaterEqual(result["meta"]["jargon_signal_count"], 1)
        jargon_categories = {item["category"] for item in result["jargon_signals"]}
        self.assertTrue({"alignment", "closure", "ownership", "schedule"} & jargon_categories)
        self.assertTrue(result["knowledge_context"]["jargon_coverage"])
        self.assertGreaterEqual(result["meta"]["org_dynamics_signal_count"], 1)
        self.assertTrue(result["org_dynamics_signals"])
        self.assertTrue(all(s["status"] == "organizational_dynamics_signal_not_fact" for s in result["org_dynamics_signals"]))
        self.assertGreaterEqual(result["meta"]["org_dynamics_pattern_count"], 1)
        self.assertTrue(result["org_dynamics_patterns"])
        self.assertTrue(all(p["status"] in {"signal_cluster", "pattern_candidate"} for p in result["org_dynamics_patterns"]))
        self.assertTrue(result["responsibility_chain"])
        self.assertTrue(result["decision_trail"])
        self.assertTrue(result["resource_map"])
        self.assertGreaterEqual(result["evidence_event_summary"]["private_count"], 1)
        self.assertTrue(result["knowledge_context"]["org_dynamics_coverage"])
        frame_ids = {frame["id"] for frame in result["knowledge_context"]["active_frames"]}
        self.assertTrue({"raci", "decision_record", "boundary_setting", "organizational_dynamics"} & frame_ids)

    async def test_org_importer_accepts_image_and_text_with_vlm(self):
        async def fake_vlm(prompt, image_paths):
            self.assertTrue(image_paths)
            return """
            {
              "people": [
                {"name": "张伟", "title": "产品负责人", "department": "Product", "manager": "王强"},
                {"name": "王强", "title": "部门经理", "department": "Platform", "manager": ""}
              ]
            }
            """

        tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        importer = OrgStructureImporter(vlm_func=fake_vlm)
        result = await importer.import_structure(
            text="补充：截图里的箭头表示直属汇报。",
            images=[{"base64": tiny_png, "mime_type": "image/png", "name": "org.png"}],
        )
        org = result["org_structure"]
        self.assertEqual(2, org["summary"]["person_count"])
        self.assertEqual(1, org["summary"]["reporting_line_count"])
        self.assertTrue(result["import_summary"]["vlm_used"])

    async def test_model_router_fails_over_to_next_provider(self):
        manager = ModelConfigManager()
        manager.providers = [
            ProviderConfig(id="bad", label="Bad", api_key="bad-key", model="bad-model", priority=1),
            ProviderConfig(id="good", label="Good", api_key="good-key", model="good-model", priority=2),
        ]
        router = ModelRouter(manager)
        calls = []

        async def fake_call(provider, *, messages, images, vision):
            calls.append(provider.id)
            if provider.id == "bad":
                raise RuntimeError("provider down")
            return "ok"

        router._call_provider = fake_call
        result = await router.generate_text("hello")
        self.assertEqual("ok", result)
        self.assertEqual(["bad", "good"], calls)
        self.assertEqual("good", manager.last_failover["used_provider"])

    async def test_memory_migration_preserves_legacy_org_chart(self):
        legacy_memory = {
            "session_id": "legacy_session",
            "person_profiles": [
                {"name": "张伟", "team": "Product", "observed_patterns": ["推动很快"]}
            ],
            "org_chart": [
                {"name": "张伟", "title": "产品负责人", "team": "Product", "reports_to": "王强"},
                {"name": "王强", "title": "部门经理", "dept": "Platform"},
            ],
            "relationships": [
                {"source": "张伟", "target": "王强", "type": "formal_reports_to", "label": "汇报"}
            ],
        }

        migrated = WorkplaceMemoryMigrator().preview_memory_migration(legacy_memory)
        memory_data = migrated["memory_data"]
        org = memory_data["org_structure"]

        self.assertEqual(CURRENT_MEMORY_SCHEMA_VERSION, memory_data["schema_version"])
        self.assertTrue(migrated["migration"]["changed"])
        self.assertEqual(2, org["summary"]["person_count"])
        self.assertEqual(1, org["summary"]["reporting_line_count"])
        self.assertIn("张伟", memory_data["person_profiles"])
        self.assertTrue(memory_data["migration_history"])


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
    def test_api_config_endpoint(self):
        client = TestClient(app)
        response = client.get("/api/v1/config")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["capabilities"]["org_import"])
        self.assertTrue(payload["capabilities"]["memory_migration"])
        self.assertIn("vlm_configured", payload["runtime"])
        self.assertIn("model_settings", payload["runtime"])

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_api_model_settings_endpoint(self):
        client = TestClient(app)
        response = client.get("/api/v1/settings/model")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["settings"]["providers"])
        self.assertTrue(payload["settings"]["templates"])

        updated = client.put(
            "/api/v1/settings/model",
            json={
                "auto_failover": False,
                "active_template_id": "workplace_politics",
                "providers": [
                    {
                        "id": "deepseek",
                        "enabled": True,
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-test-key-1234",
                        "model": "deepseek-chat",
                    }
                ],
            },
        )
        self.assertEqual(200, updated.status_code)
        settings = updated.json()["settings"]
        self.assertFalse(settings["auto_failover"])
        self.assertEqual("workplace_politics", settings["active_template_id"])
        deepseek_provider = [p for p in settings["providers"] if p["id"] == "deepseek"][0]
        self.assertEqual("https://api.deepseek.com", deepseek_provider["base_url"])
        self.assertEqual("deepseek-chat", deepseek_provider["model"])
        self.assertEqual("sk-t...1234", deepseek_provider["api_key"])

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
        self.assertIn("person_histories", payload)
        self.assertIn("org_structure", payload)

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_api_org_structure_endpoints(self):
        client = TestClient(app)
        response = client.post(
            "/api/v1/org-structure",
            json={
                "session_id": "org_test_session",
                "org_structure": {
                    "departments": [{"id": "dept_product", "name": "Product", "people_count": 1}],
                    "people": [{"id": "p1", "name": "张伟", "title": "产品负责人", "department": "Product", "manager": "王强"}],
                    "reporting_lines": [{"source_name": "张伟", "target_name": "王强", "type": "formal_reports_to"}],
                    "department_tree": [],
                    "reporting_tree": [],
                    "summary": {"department_count": 1, "person_count": 1, "reporting_line_count": 1},
                },
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["success"])
        get_response = client.get("/api/v1/org-structure/org_test_session")
        self.assertEqual(200, get_response.status_code)
        org_payload = get_response.json()["org_structure"]
        self.assertEqual("Product", org_payload["departments"][0]["name"])

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_api_org_structure_import_text_fallback(self):
        client = TestClient(app)
        response = client.post(
            "/api/v1/org-structure/import",
            json={
                "session_id": "org_import_text_session",
                "text": "组织架构：张伟 - 产品负责人 - Product 团队 - 汇报王强\n组织架构：王强 - 部门经理 - Platform 部门",
                "images": [],
                "use_vlm": False,
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(2, payload["org_structure"]["summary"]["person_count"])
        self.assertEqual(1, payload["org_structure"]["summary"]["reporting_line_count"])

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_api_memory_migration_preview(self):
        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/migrate",
            json={
                "session_id": "migration_preview_session",
                "memory_data": {
                    "session_id": "legacy_session",
                    "person_profiles": [{"name": "李娜", "team": "Product"}],
                    "org_chart": [{"name": "李娜", "title": "资深同事", "team": "Product"}],
                },
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["migration"]["changed"])
        self.assertEqual(CURRENT_MEMORY_SCHEMA_VERSION, payload["memory_data"]["schema_version"])
        self.assertEqual(1, payload["memory_data"]["org_structure"]["summary"]["person_count"])

    @unittest.skipIf(TestClient is None or app is None, "fastapi is not installed")
    def test_home_serves_graph_ui(self):
        client = TestClient(app)
        response = client.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("职场关系雷达", response.text)


if __name__ == "__main__":
    unittest.main()
