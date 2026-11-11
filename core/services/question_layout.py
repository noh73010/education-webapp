"""Read-only presentation of question text. Never changes stored learning content."""
import re

TAG = re.compile(r'\[(CONTEXT|TABLE|DATA|RULES|TEXT|QUESTION)\](.*?)\[/\1\]', re.S | re.I)
LABELS = {'CONTEXT': '상황·자료', 'TABLE': '입력 데이터', 'DATA': '입력 데이터',
          'RULES': '조건', 'TEXT': '입력값', 'QUESTION': '질문',
          'OPTIONS': '보기', 'CONDITIONS': '조건'}
# Require whitespace after a marker: references such as '(ㄱ)과' are not list items.
MARKER = re.compile(r'(?<!\S)(?:([ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ])[.:：．]|\(([ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ])\)|([A-Z])[.:：])\s+')
SENTENCE = re.compile(r'(?<![ㄱ-ㅎA-Z]\.)(?<=[.!?。？！])\s+')
CONDITION = re.compile(r'^(?:단(?:[,，\s]|$)|다만[,，\s]|각 요인은|각 경력은|본래 용도의|다툼이|ㄱ·ㄷ은|거치기간은|조례·|비과세·|특례는|다른 조건|특별한|별도 |다른 약정|일반적인 계약|\d{4}년.*기준으로 판단)')


def block(kind, content, items=None):
    result = {'type': kind, 'label': LABELS[kind], 'content': content.strip()}
    if items:
        result['statements'] = [item.rstrip(' /') for item in items]
    return result


def prose(text, kind):
    """Keep sentence text and order, separating independently stated conditions."""
    result = []
    for sentence in SENTENCE.split(text.strip()):
        if not sentence:
            continue
        current = 'CONDITIONS' if CONDITION.match(sentence) else kind
        if result and result[-1]['type'] == current:
            result[-1]['content'] += '\n' + sentence
        else:
            result.append(block(current, sentence))
    return result


def marked(text, fallback):
    matches = list(MARKER.finditer(text))
    letters = [next(g for g in m.groups() if g) for m in matches]
    # Two sequential markers are evidence of a list, rather than a reference.
    alphabet = 'ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ' if letters and letters[0] == 'ㄱ' else 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if len(matches) < 2 or ''.join(letters) != alphabet[:len(letters)]:
        return prose(text, fallback)
    result = prose(text[:matches[0].start()], fallback)
    items = [text[m.start():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()
             for i, m in enumerate(matches)]
    # A shared constraint after the final item belongs to the whole question.
    tail = []
    last = SENTENCE.split(items[-1])
    for i, sentence in enumerate(last[1:], 1):
        if CONDITION.match(sentence):
            items[-1] = ' '.join(last[:i])
            tail = prose(' '.join(last[i:]), 'CONDITIONS')
            break
    result.append(block('OPTIONS', '\n'.join(items), items))
    return result + tail


def plain_blocks(text):
    text = text.strip()
    if not text:
        return []
    question = re.search(r'[?？]', text)
    if not question:
        return marked(text, 'QUESTION')
    head, tail = text[:question.end()], text[question.end():]
    # The final sentence asks the question; earlier sentences supply its context.
    starts = list(SENTENCE.finditer(head))
    start = starts[-1].end() if starts else 0
    # A marker's period is not a sentence boundary. A single inline construction
    # ('건축법령상 ㄱ: ... ㄷ: ... 중 대수선...') needs its own exact boundary.
    head_markers = list(MARKER.finditer(head))
    if len(head_markers) >= 2 and head_markers[-1].end() > start:
        boundary = head.find(' 중 대수선에 해당하는 것만 고른 것은?')
        if boundary >= 0:
            return marked(head[:boundary], 'CONTEXT') + [block('QUESTION', head[boundary:])] + marked(tail, 'CONDITIONS')
        return marked(head, 'QUESTION') + marked(tail, 'CONDITIONS')
    result = marked(head[:start], 'CONTEXT')
    result.append(block('QUESTION', head[start:]))
    if tail.strip():
        # Unmarked post-question text is explicitly supplied material or a constraint.
        if len(list(MARKER.finditer(tail))) >= 2:
            result.extend(marked(tail, 'CONTEXT'))
        else:
            for sentence in SENTENCE.split(tail.strip()):
                data_start = ("'", '“', '「', 'A사는', 'A화물은', '공급량은', '톤당 운송비는',
                              '철도 컨테이너', '그림은', '준공업지역,', '연면적 ', '설립을 준비할', '순서대로 ')
                kind = 'CONTEXT' if sentence.startswith(data_start) else 'CONDITIONS'
                result.append(block(kind, sentence))
    return result


def question_blocks(prompt):
    prompt = str(prompt or '')
    matches = list(TAG.finditer(prompt))
    if not matches:
        return plain_blocks(prompt)
    # Retain untagged text around blocks as well (older rendering silently lost it).
    result, offset = [], 0
    for match in matches:
        result.extend(plain_blocks(prompt[offset:match.start()]))
        kind, text = match.group(1).upper(), match.group(2).strip()
        if text:
            result.append(block(kind, text))
        offset = match.end()
    result.extend(plain_blocks(prompt[offset:]))
    return result
