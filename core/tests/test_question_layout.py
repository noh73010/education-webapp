import csv
import re
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core.services.question_layout import question_blocks


class QuestionLayoutTests(SimpleTestCase):
    def compact(self, text):
        return re.sub(r'\s+', '', text)

    def test_question_statements_and_shared_condition(self):
        prompt = ('정상재인 아파트의 균형가격을 상승시키는 요인만을 모두 고른 것은? '
                  'ㄱ: 가구 실질소득 증가. ㄴ: 건축자재 가격 하락. '
                  'ㄷ: 아파트 선호 증가. ㄹ: 주택담보대출 금리 상승. '
                  '각 요인은 독립적으로 발생하며 다른 조건은 동일하다.')
        blocks = question_blocks(prompt)
        self.assertEqual([b['type'] for b in blocks], ['QUESTION', 'OPTIONS', 'CONDITIONS'])
        self.assertEqual(len(blocks[1]['statements']), 4)
        self.assertNotIn('다른 조건', blocks[1]['statements'][-1])
        self.assertIn('각 요인은', blocks[-1]['content'])
        html = render_to_string('core/includes/question_prompt.html', {'prompt': prompt})
        self.assertEqual(html.count('<li>'), 4)
        self.assertEqual(html.count('<ul '), 1)
        self.assertNotIn("('type',", html)

    def test_context_before_question_and_decimal_values(self):
        blocks = question_blocks('연비는 6.5km/L이다. 거리는 180.5km이다. 총 연료량은? 단, 반올림한다.')
        self.assertEqual([b['type'] for b in blocks], ['CONTEXT', 'QUESTION', 'CONDITIONS'])
        self.assertIn('180.5km', blocks[0]['content'])
        self.assertEqual(blocks[1]['content'], '총 연료량은?')

    def test_blank_references_are_not_list_markers(self):
        blocks = question_blocks('책임지는 자를 (ㄱ)이라 한다. 포괄 용어를 (ㄴ)이라 한다. (ㄱ)과 (ㄴ)의 연결은?')
        self.assertNotIn('OPTIONS', [b['type'] for b in blocks])
        blocks = question_blocks('연결은? (ㄱ) 첫 사례 (ㄴ) 두 번째 사례')
        self.assertEqual(len(blocks[-1]['statements']), 2)

    def test_latin_cases_and_slash_separators(self):
        blocks = question_blocks('사례의 연결은? A: 거래 사례 / B: 운송 사례')
        self.assertEqual(blocks[-1]['statements'], ['A: 거래 사례', 'B: 운송 사례'])
        # Raw block content still records all punctuation, including separators.
        self.assertIn('/', blocks[-1]['content'])

    def test_cases_before_question_keep_source_order(self):
        prompt = '각 사례는 다음과 같다. ㄱ: 첫 사례 / ㄴ: 두 번째 사례이다. 옳은 것은? 다툼이 있으면 판례에 따른다.'
        blocks = question_blocks(prompt)
        self.assertEqual([b['type'] for b in blocks], ['CONTEXT', 'OPTIONS', 'QUESTION', 'CONDITIONS'])
        self.assertEqual(self.compact(''.join(b['content'] for b in blocks)), self.compact(prompt))

    def test_structured_prompts_keep_untagged_text_and_table_lines(self):
        blocks = question_blocks('안내문. [TABLE]A | B\n1 | 2[/TABLE] [QUESTION]값은?[/QUESTION] 단, 반올림한다.')
        self.assertEqual(blocks[1]['content'], 'A | B\n1 | 2')
        self.assertEqual(blocks[0]['content'], '안내문.')
        self.assertEqual(blocks[-1]['type'], 'CONDITIONS')

    def test_unrecognized_or_empty_text_is_not_dropped(self):
        self.assertEqual(question_blocks(''), [])
        text = 'ㄴ. 단독 참조를 포함한 설명문이다.'
        self.assertEqual(question_blocks(text)[0]['content'], text)

    def test_html_remains_escaped(self):
        html = render_to_string('core/includes/question_prompt.html', {'prompt': '<script>alert(1)</script> 값은? ㄱ. <b>첫째</b> ㄴ. 둘째'})
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('question-statements', html)

    def test_all_catalog_prompts_retain_content_and_split_all_lists(self):
        root = Path(settings.BASE_DIR) / 'generated'
        files = sorted((root / 'logistics').glob('*.csv')) + sorted((root / 'realtor').glob('*.csv'))
        count = 0
        for path in files:
            with path.open(encoding='utf-8-sig', newline='') as source:
                for row in csv.DictReader(source):
                    prompt = row['문제']
                    with self.subTest(id=row['문항ID']):
                        blocks = question_blocks(prompt)
                        self.assertEqual(self.compact(''.join(b['content'] for b in blocks)), self.compact(prompt))
                        self.assertTrue(any(b['type'] == 'QUESTION' for b in blocks))
                        if re.search(r'(?<!\S)ㄱ[.:：]', prompt) and re.search(r'(?<!\S)ㄴ[.:：]', prompt):
                            self.assertTrue(any(b.get('statements') for b in blocks))
                    count += 1
        self.assertGreaterEqual(count, 1400)
