"""OpenAI Responses API text grader using only the Python standard library.
Uses the existing LAS-VICA score_candidate() validation and metrics code.
"""
import json
import os
import time
import urllib.error
import urllib.request

class BudgetExceeded(RuntimeError):
    pass

class OpenAIScorer:
    def __init__(self, model='gpt-5-mini', max_output_tokens=2000,
                 max_usd=50.0, input_usd_per_m=0.25, output_usd_per_m=2.0,
                 usage_log='results/scoring/api_usage.jsonl', timeout=180):
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.max_usd = max_usd
        self.input_rate = input_usd_per_m
        self.output_rate = output_usd_per_m
        self.usage_log = usage_log
        self.timeout = timeout
        self.spent = 0.0
        if os.path.exists(usage_log):
            with open(usage_log, encoding='utf-8') as fh:
                for line in fh:
                    try:
                        event = json.loads(line)
                        if event.get('model') == model:
                            self.spent += float(event.get('estimated_usd', 0))
                    except (ValueError, TypeError):
                        continue

    def __enter__(self):
        if not os.environ.get('OPENAI_API_KEY'):
            raise RuntimeError('Set OPENAI_API_KEY before running the API scorer')
        return self

    def __exit__(self, *_):
        pass

    def score(self, prompt):
        # Reserve a conservative amount for the current call before spending.
        estimated_input_tokens = max(1, len(prompt) // 3)
        reservation = (estimated_input_tokens * self.input_rate +
                       self.max_output_tokens * self.output_rate) / 1_000_000
        if self.spent + reservation > self.max_usd:
            raise BudgetExceeded(f'Budget guard: estimated ${self.spent:.4f} spent, '
                                 f'${reservation:.4f} reserved, ${self.max_usd:.2f} cap')
        payload = {
            'model': self.model,
            'instructions': 'Return a single valid JSON object only. No Markdown.',
            'input': prompt,
            'max_output_tokens': self.max_output_tokens,
            'text': {'format': {'type': 'json_object'}},
        }
        request = urllib.request.Request(
            'https://api.openai.com/v1/responses',
            data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                     'Content-Type': 'application/json'}, method='POST')
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    result = json.load(response)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode('utf-8', errors='replace')[:1500]
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f'API HTTP {exc.code}: {detail}') from exc
                time.sleep(2 ** attempt)
            except (TimeoutError, urllib.error.URLError):
                # No automatic retry on uncertain network delivery: avoid double billing.
                raise
        output = ''.join(c.get('text', '') for item in result.get('output', [])
                         for c in item.get('content', []) if c.get('type') == 'output_text')
        usage = result.get('usage') or {}
        input_tokens = int(usage.get('input_tokens') or 0)
        output_tokens = int(usage.get('output_tokens') or 0)
        cost = (input_tokens * self.input_rate + output_tokens * self.output_rate) / 1_000_000
        self.spent += cost
        os.makedirs(os.path.dirname(os.path.abspath(self.usage_log)), exist_ok=True)
        with open(self.usage_log, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'model': self.model, 'response_id': result.get('id'),
                                 'input_tokens': input_tokens, 'output_tokens': output_tokens,
                                 'estimated_usd': cost, 'cumulative_session_usd': self.spent,
                                 'rates_usd_per_m': [self.input_rate, self.output_rate]}) + '\n')
        if not output.strip():
            raise RuntimeError('API response had no output text; inspect token budget or model')
        return output
