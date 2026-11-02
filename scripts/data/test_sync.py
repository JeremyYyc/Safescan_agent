from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sync import command_for, create_plan, main, select_steps
from validate_execution_dataset import TABLES


class ManualSyncTests(unittest.TestCase):
    def test_dependency_order_and_duplicate_selection(self):
        self.assertEqual(select_steps("lease-pdf,city,staff,staff,dataset"),
                         ["staff", "dataset", "city", "lease-pdf"])

    def test_unknown_step_fails_before_execution(self):
        with self.assertRaises(ValueError):
            select_steps("staff,deploy")

    def test_dry_run_never_runs_docker_or_creates_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-created"
            with patch("sync.subprocess.run") as run:
                self.assertEqual(main(["--steps", "staff,lease-pdf", "--output-dir", str(output)]), 0)
            run.assert_not_called()
            self.assertFalse(output.exists())

    def test_dataset_plan_requires_every_jsonl_before_service_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = Namespace(steps="dataset", source_dir=root, collection_dir=None)
            (root / "execution_units.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "missing source files"):
                create_plan(args)
            for name in TABLES:
                (root / (name + ".jsonl")).write_text("")
            self.assertEqual(create_plan(args)[0]["source_dir"], str(root.resolve()))

    def test_media_can_cover_both_source_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execution, collection = root / "execution", root / "collection"
            for folder in (execution, collection):
                folder.mkdir()
                (folder / "objects.json").write_text("[]")
            plan = create_plan(Namespace(steps="media", source_dir=execution, collection_dir=collection))
            self.assertEqual([item["source_dir"] for item in plan], [str(execution.resolve()), str(collection.resolve())])

    def test_default_plan_explicitly_prepares_city_before_dataset_and_reconciles_after(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in TABLES:
                (root / (name + ".jsonl")).write_text("")
            (root / "objects.json").write_text("[]")
            plan = create_plan(Namespace(steps=None, source_dir=root, collection_dir=None))
            self.assertEqual([(item["step"], item.get("phase")) for item in plan],
                             [("staff", None), ("city", "prepare"), ("dataset", None),
                              ("media", None), ("city", "reconcile"), ("lease-pdf", None)])

    def test_city_preparation_is_only_added_when_both_steps_are_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in TABLES:
                (root / (name + ".jsonl")).write_text("")
            city = create_plan(Namespace(steps="city", source_dir=root, collection_dir=None))
            self.assertEqual([(item["step"], item.get("phase")) for item in city], [("city", "reconcile")])
            data = create_plan(Namespace(steps="dataset", source_dir=root, collection_dir=None))
            self.assertEqual([item["step"] for item in data], ["dataset"])

    def test_apply_commands_use_one_off_containers_and_read_only_sources(self):
        args = Namespace(env_file=None, project_name="isolated-test", output_dir=Path("/tmp/outputs"),
                         create_buckets=False)
        command = command_for(args, {"step": "dataset", "service": "property-leasing-service",
                                     "source_dir": "/tmp/export with spaces"})
        self.assertIn("run", command)
        self.assertIn("--no-deps", command)
        self.assertIn("/tmp/export with spaces:/source:ro", command)
        self.assertNotIn("up", command)
        self.assertNotIn("--mount", command)  # Compose run supports --volume.

    def test_default_deployment_has_no_seed_or_document_sync(self):
        root = Path(__file__).resolve().parents[2]
        compose = (root / "docker-compose.yml").read_text()
        identity = compose.split("  identity-access-service:", 1)[1].split("  property-leasing-service:", 1)[0]
        properties = compose.split("  property-leasing-service:", 1)[1].split("  property-leasing-worker:", 1)[0]
        documents = compose.split("  property-leasing-document-worker:", 1)[1].split("  property-leasing-outbox-worker:", 1)[0]
        self.assertNotIn("python -m app.seed", identity + properties)
        self.assertNotIn("python -m app.bootstrap_admin", identity)
        self.assertIn("profiles: [data-sync]", documents)
        dockerfile = (root / "backend/services/identity-access-service/Dockerfile").read_text()
        self.assertNotIn("python -m app.seed_staff", dockerfile)


if __name__ == "__main__":
    unittest.main()
