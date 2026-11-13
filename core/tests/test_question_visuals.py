import csv
import hashlib
import re
import heapq
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core.services.question_visuals import _catalog, question_visual


class ReadableQuestionFigureTests(SimpleTestCase):
    def render(self, path):
        mission = SimpleNamespace(
            id=42, course="보관하역론", subject=SimpleNamespace(name="물류관리사"),
            question_image=SimpleNamespace(static_path=path),
        )
        return render_to_string("core/includes/mission_image.html", {"mission": mission})

    def test_representations_apply_only_to_active_inspected_asset_bytes(self):
        root = Path(settings.BASE_DIR)
        active = set()
        for path in (root / "generated" / "logistics").glob("*.csv"):
            with path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    active.add(row.get("문제이미지") or row.get("이미지") or "")
        for path, visual in _catalog().items():
            with self.subTest(path=path):
                self.assertIn(path, active)
                self.assertEqual(
                    hashlib.sha256((root / "core/static" / path).read_bytes()).hexdigest(),
                    visual["sha256"],
                )
                self.assertIsNotNone(question_visual(path))
                for panel in visual.get("panels", []):
                    self.assertGreater(panel["width"], 0)
                    self.assertGreater(panel["height"], 0)
                    self.assertGreaterEqual(panel["x"], 0)
                    self.assertGreaterEqual(panel["y"], 0)
                    self.assertLessEqual(panel["x"] + panel["width"], visual["width"])
                    self.assertLessEqual(panel["y"] + panel["height"], visual["height"])

    def test_intentionally_false_propositions_remain_unmarked_question_material(self):
        html = self.render("images/questions/logistics/29회-2/q003_r20261113.webp")
        self.assertIn("항만 배후지역에만 설치되며 내륙에는 설치되지 않는다.", html)
        self.assertIn("단일 운송수단만을 이용하여", html)
        self.assertNotIn("정답", html)
        self.assertNotIn("<button", html)
        self.assertNotIn("<dialog", html)
        self.assertNotIn("question-image-full", html)

    def test_comparison_keeps_the_wrong_row_and_all_other_rows(self):
        html = self.render("images/questions/logistics/29회-1/q104_r20261113.webp")
        self.assertIn('data-column-label="정기선운송">시장운임에 의한 경쟁 운임', html)
        self.assertIn('data-column-label="부정기선운송">운임표에 따른 운임 적용', html)
        self.assertEqual(html.count('scope="row"'), 5)
        self.assertNotIn("정답", html)

    def test_all_four_sorter_panels_are_present_in_order_without_answer_names(self):
        html = self.render("images/questions/logistics/29회-2/q013_r20261113.webp")
        self.assertEqual(html.count('class="question-figure-crop"'), 4)
        positions = [html.index(f'aria-label="{letter}"') for letter in "ABCD"]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("팝업", html)
        self.assertNotIn("틸트", html)

    def test_unseen_versions_and_historical_images_use_the_original_renderer(self):
        for path in ("images/questions/logistics/29회-2/q003.png",
                     "images/questions/logistics/29회-2/q003_future.webp"):
            with self.subTest(path=path):
                self.assertIsNone(question_visual(path))
                html = self.render(path)
                self.assertIn('class="question-image"', html)
                self.assertNotIn("data-question-figure", html)

    def test_replaced_image_does_not_show_stale_transcribed_text(self):
        path = "images/questions/logistics/29회-2/q003_r20261113.webp"
        with patch("core.services.question_visuals._asset_matches", return_value=False):
            self.assertIsNone(question_visual(path))
            html = self.render(path)
        self.assertNotIn("data-question-figure", html)
        self.assertIn('class="question-image"', html)

    def test_drawn_edges_connect_the_nodes_declared_by_the_problem(self):
        for path, visual in _catalog().items():
            if visual["kind"] != "graph":
                continue
            nodes = {node["label"]: (node["x"], node["y"]) for node in visual["nodes"]}
            with self.subTest(path=path):
                for edge in visual["edges"]:
                    coordinates = [int(value) for value in re.findall(r"-?\d+", edge["path"])]
                    self.assertEqual(tuple(coordinates[:2]), nodes[edge["start"]])
                    self.assertEqual(tuple(coordinates[-2:]), nodes[edge["end"]])

    def test_readable_graphs_retain_the_csv_calculation_results(self):
        graph = _catalog()["images/questions/logistics/26회-1/q071_r20261113.webp"]
        parent = {node["label"]: node["label"] for node in graph["nodes"]}

        def root(label):
            while parent[label] != label:
                label = parent[label]
            return label

        total, selected = 0, 0
        for edge in sorted(graph["edges"], key=lambda edge: edge["weight"]):
            a, b = root(edge["start"]), root(edge["end"])
            if a != b:
                parent[a] = b
                total += edge["weight"]
                selected += 1
        self.assertEqual((total, selected), (26, 7))
        graph = _catalog()["images/questions/logistics/29회-1/q065_r20261113.webp"]
        distance, queue = {"S": 0}, [(0, "S")]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != distance[node]:
                continue
            for edge in graph["edges"]:
                if node not in (edge["start"], edge["end"]):
                    continue
                other = edge["end"] if node == edge["start"] else edge["start"]
                candidate = cost + edge["weight"]
                if candidate < distance.get(other, float("inf")):
                    distance[other] = candidate
                    heapq.heappush(queue, (candidate, other))
        self.assertEqual(distance["F"], 12)
