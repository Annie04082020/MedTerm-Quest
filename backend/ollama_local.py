"""Loopback-only Ollama client. No redirects, proxies, cloud calls or model pulls."""
import time

import httpx
from pydantic import BaseModel

OLLAMA_URL = 'http://127.0.0.1:11434'
DEFAULT_MODEL = 'qwen3:4b'
FALLBACK_MODEL = 'qwen3:1.7b'


class LocalAIError(RuntimeError):
    pass


class ResourceReleaseError(LocalAIError):
    pass


def is_memory_error(error):
    return any(term in str(error).casefold() for term in ('out of memory', 'memory allocation', 'cuda error', 'cublas', 'cudnn', 'insufficient memory', 'not enough memory', 'failed to allocate', 'requires more system memory', 'cudamalloc'))


def local_model_name(name):
    return bool(name) and len(name) <= 200 and not any(x in name.lower() for x in ('cloud', '/', '\\', 'http', '@'))


class OllamaLocal:
    def request(self, method, endpoint, payload=None, timeout=4):
        try:
            with httpx.Client(base_url=OLLAMA_URL, trust_env=False, follow_redirects=False, timeout=timeout) as client:
                response = client.request(method, endpoint, json=payload)
            if response.is_redirect:
                raise LocalAIError('Ollama 重新導向已被拒絕；僅允許本機推論。')
            if response.status_code >= 400:
                raise LocalAIError(f'Ollama {response.status_code}: {response.text[:600]}')
            return response.json()
        except httpx.ReadTimeout as exc:
            if endpoint == '/api/generate':
                raise LocalAIError(f'本機 Ollama 推論逾時（等待上限 {timeout} 秒）；服務不一定離線。請釋放 GPU／RAM 或縮短輸出後重試。一般遊戲仍可使用。') from exc
            raise LocalAIError('本機 Ollama 回應逾時，可能正忙碌；請檢查服務負載後重試。') from exc
        except (httpx.RequestError, ValueError) as exc:
            raise LocalAIError('無法連線本機 Ollama。請安裝並啟動 Ollama（ollama serve）；遊戲仍可正常使用。') from exc

    def models(self):
        data = self.request('GET', '/api/tags')
        return [m for m in data.get('models', []) if local_model_name(m.get('name', ''))
                and not m.get('remote_host') and not m.get('remote_model') and m.get('size', 0) > 0]

    def check_model(self, model):
        if not local_model_name(model):
            raise LocalAIError('只允許已安裝的本機模型名稱，不允許 cloud／遠端模型。')
        available = {m['name']: m for m in self.models()}
        if model not in available:
            raise LocalAIError(f'尚未安裝 {model}。請自行確認後執行 ollama pull {model}；本程式不會下載模型。')
        info = self.request('POST', '/api/show', {'model': model})
        if info.get('remote_host') or info.get('remote_model'):
            raise LocalAIError('已拒絕指向雲端的模型；請選本機量化模型。')
        return available[model]

    def running(self):
        return self.request('GET', '/api/ps').get('models', [])

    def wait_unloaded(self, model):
        for _ in range(12):
            if not any(m.get('name', m.get('model')) == model for m in self.running()):
                return
            time.sleep(.25)
        raise LocalAIError('Ollama 尚未釋放模型，已停止後續 GPU 工作；請在 Ollama 中停止該模型後重試。')

    def unload(self, model):
        self.request('POST', '/api/generate', {'model': model, 'keep_alive': 0, 'stream': False}, timeout=30)
        self.wait_unloaded(model)

    def generate(self, model: str, prompt: str, schema: type[BaseModel], cpu=False):
        self.check_model(model)
        options = {'num_ctx': 4096, 'num_predict': 1200, 'temperature': .1}
        if cpu:
            options['num_gpu'] = 0
        original_error = None
        try:
            response = self.request('POST', '/api/generate', {
                'model': model, 'prompt': prompt, 'system': 'Return only schema-compliant JSON. /no_think',
                'think': False, 'stream': False, 'format': schema.model_json_schema(),
                'options': options, 'keep_alive': 0,
            }, timeout=180)
            if response.get('done_reason') == 'length':
                raise LocalAIError('模型輸出超過長度上限；請縮短來源片段或選較簡單的題型。')
            if not response.get('done', True):
                raise LocalAIError('模型未完成回覆，未保存任何未驗證題目。')
            content = response.get('response', '')
            if len(content) > 24000:
                raise LocalAIError('模型回覆過長，已拒絕。')
            return schema.model_validate_json(content)
        except Exception as exc:
            original_error = exc
            raise
        finally:
            # Explicit unload also covers invalid JSON and failed generation.
            try:
                self.unload(model)
            except LocalAIError as exc:
                raise ResourceReleaseError('無法確認模型已釋放，已停止自動 fallback。請停止 Ollama 模型後重試。 '+str(original_error or exc)) from exc
