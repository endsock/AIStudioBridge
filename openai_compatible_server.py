# openai_compatible_server.py

import requests
import json
import time
import sys
import re
import uuid
from flask import Flask, request, Response, jsonify
from flask_cors import CORS # 【【【新】】】 引入 CORS

# --- 配置 ---
PUBLIC_PORT = 5100 
INTERNAL_SERVER_URL = "http://127.0.0.1:5101"
END_OF_STREAM_SIGNAL = "__END_OF_STREAM__"

app = Flask(__name__)
# --- 【【【核心修复：为整个应用启用 CORS】】】 ---
# 这将自动处理所有 OPTIONS 预检请求，并添加必要的 Access-Control-* 头信息。
CORS(app)
# --- 【【【修复结束】】】 ---

LAST_CONVERSATION_STATE = None

def check_internal_server():
    print("...正在检查内部服务器状态...")
    try:
        response = requests.get(INTERNAL_SERVER_URL, timeout=3)
        if response.status_code == 200:
            print(f"✅ 内部服务器 (在 {INTERNAL_SERVER_URL}) 连接成功！")
            return True
    except requests.exceptions.RequestException:
        print("\n" + "!"*60)
        print("!! 致命错误：无法连接到内部服务器！")
        print(f"!! 请确保 `local_history_server.py` 已经启动并且正在 {INTERNAL_SERVER_URL} 上运行。")
        print("!"*60)
        return False

def _normalize_message_content(message: dict) -> dict:
    content = message.get("content")
    if isinstance(content, list):
        all_text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                all_text_parts.append(part.get("text", ""))
        message["content"] = "\n\n".join(all_text_parts)
    return message

def _inject_history(job_payload: dict, wait_time: int = 10):
    try:
        requests.post(f"{INTERNAL_SERVER_URL}/submit_injection_job", json=job_payload).raise_for_status()
        time.sleep(wait_time)
        return True
    except requests.exceptions.RequestException as e: return False

def _submit_prompt(prompt: str):
    try:
        response = requests.post(f"{INTERNAL_SERVER_URL}/submit_prompt", json={"prompt": prompt})
        response.raise_for_status()
        return response.json()['task_id']
    except requests.exceptions.RequestException as e: return None

def format_openai_chunk(content: str, model: str, request_id: str):
    chunk_data = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
    return f"data: {json.dumps(chunk_data)}\n\n"

def format_openai_finish_chunk(model: str, request_id: str):
    chunk_data = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
    return f"data: {json.dumps(chunk_data)}\n\n"

def stream_and_update_state(task_id: str, request_base: dict, final_prompt: str):
    global LAST_CONVERSATION_STATE
    model = request_base.get("model", "gemini-custom")
    request_id = f"chatcmpl-{uuid.uuid4()}"
    text_pattern = re.compile(r'\[\s*null\s*,\s*\"((?:\\.|[^\"\\])*)\"(?:\s*,\s*\"model\")?\s*\]')
    buffer = ""
    full_ai_response_text = ""
    stream_ended_properly = False
    start_time = time.time()
    while time.time() - start_time < 120:
        try:
            res = requests.get(f"{INTERNAL_SERVER_URL}/get_chunk/{task_id}", timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data['status'] == 'ok':
                    chunk_content = data.get('chunk')
                    if chunk_content == END_OF_STREAM_SIGNAL:
                        stream_ended_properly = True; break
                    buffer += chunk_content
                    last_pos = 0
                    for match in text_pattern.finditer(buffer):
                        try:
                            text = json.loads(f'"{match.group(1)}"')
                            full_ai_response_text += text
                            yield format_openai_chunk(text, model, request_id)
                        except json.JSONDecodeError: continue
                        last_pos = match.end()
                    buffer = buffer[last_pos:]
                elif data['status'] == 'done':
                    stream_ended_properly = True; break
            time.sleep(0.05)
        except requests.exceptions.RequestException: time.sleep(1)
    if stream_ended_properly:
        new_state = request_base.copy()
        new_state["messages"].append({"role": "user", "content": final_prompt})
        new_state["messages"].append({"role": "assistant", "content": full_ai_response_text})
        LAST_CONVERSATION_STATE = new_state
        print("✅ [Cache] 会话状态已正确更新。")
    else:
        LAST_CONVERSATION_STATE = None
        print("⚠️ [Cache] 流未正常结束，会话缓存已清空。")
    yield format_openai_finish_chunk(model, request_id)
    yield "data: [DONE]\n\n"

@app.route('/reset_state', methods=['POST'])
def reset_state():
    global LAST_CONVERSATION_STATE
    LAST_CONVERSATION_STATE = None
    print("🔄 [Cache] 会话缓存已被手动重置。")
    return jsonify({"status": "success", "message": "Conversation cache has been reset."})

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    # OPTIONS请求由Flask-CORS自动处理，我们不需要显式地处理它。
    # 当真正的POST请求到达时，这个函数才会执行。
    if request.method == 'OPTIONS':
        return '', 200

    global LAST_CONVERSATION_STATE
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 接收到新的 /v1/chat/completions 请求...")
    request_data = request.json
    try:
        messages = [_normalize_message_content(msg) for msg in request_data.get("messages", [])]
        request_data["messages"] = messages
    except Exception as e: return f"错误：处理消息内容时失败: {e}", 400
    if not request_data.get('stream', False): return "错误：此服务器仅支持流式响应 (stream: true)。", 400
    if not messages: return "错误: 'messages' 列表不能为空。", 400

    is_continuation = False
    if LAST_CONVERSATION_STATE:
        cached_messages = LAST_CONVERSATION_STATE.get("messages", [])
        new_messages_base = messages[:-1]
        cached_dump = json.dumps(cached_messages, sort_keys=True)
        new_base_dump = json.dumps(new_messages_base, sort_keys=True)
        if cached_dump == new_base_dump and messages[-1].get("role") == "user":
            is_continuation = True
    
    if is_continuation:
        print("⚡️ [Fast Path] 检测到连续对话，跳过页面刷新。")
        final_prompt = messages[-1].get("content")
        request_base_for_update = request_data.copy()
        request_base_for_update["messages"] = messages[:-1]
        task_id = _submit_prompt(final_prompt)
        if task_id: return Response(stream_and_update_state(task_id, request_base_for_update, final_prompt), mimetype='text/event-stream')
        else:
            LAST_CONVERSATION_STATE = None
            return "错误：快速通道提交Prompt失败，请重试（将执行完整注入）。", 500
    else:
        print("🔄 [Full Injection] 检测到新对话或状态不一致，执行完整页面注入。")
        LAST_CONVERSATION_STATE = None
        injection_payload = request_data.copy()
        final_prompt = None
        if messages[-1].get("role") == "user":
            injection_payload["messages"] = messages[:-1]
            final_prompt = messages[-1].get("content")
        if _inject_history(injection_payload):
            if final_prompt:
                task_id = _submit_prompt(final_prompt)
                if task_id: return Response(stream_and_update_state(task_id, injection_payload, final_prompt), mimetype='text/event-stream')
            else:
                LAST_CONVERSATION_STATE = injection_payload
                print("✅ [Cache] 仅注入任务完成，会话状态已更新。")
                def empty_stream():
                    yield format_openai_finish_chunk(request_data.get("model", "gemini-custom"), f"chatcmpl-{uuid.uuid4()}")
                    yield "data: [DONE]\n\n"
                return Response(empty_stream(), mimetype='text/event-stream')
    return "错误：未能处理请求，出现未知错误。", 500

if __name__ == "__main__":
    if not check_internal_server(): sys.exit(1)
    print("="*60)
    print("  OpenAI 兼容 API 网关 v2.5 (The CORS Guardian)")
    print("="*60)
    print("  ✨ 新功能: 已启用 CORS 支持，可以处理来自任何前端应用的跨域请求。")
    print("\n  运行指南:")
    print("  1. ✅ `local_history_server.py` 已成功连接。")
    print("  2. ✅ 确保浏览器和油猴脚本已就绪。")
    print(f"  3. 🚀 本 API 服务器正在 http://127.0.0.1:{PUBLIC_PORT} 上运行。")
    print("="*60)
    app.run(host='0.0.0.0', port=PUBLIC_PORT, threaded=True)