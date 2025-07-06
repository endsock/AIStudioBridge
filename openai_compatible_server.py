# openai_compatible_server.py (v5.1 - Robust Tool Handling)

import requests
import json
import time
import sys
import re
import uuid
from flask import Flask, request, Response, jsonify
from flask_cors import CORS

# --- 配置 ---
PUBLIC_PORT = 5100
INTERNAL_SERVER_URL = "http://127.0.0.1:5101"
END_OF_STREAM_SIGNAL = "__END_OF_STREAM__"

app = Flask(__name__)
CORS(app)

LAST_CONVERSATION_STATE = None

# --- OpenAI 格式化辅助函数 (升级) ---

# 【流式】文本块
def format_openai_chunk(content: str, model: str, request_id: str):
    chunk_data = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
    return f"data: {json.dumps(chunk_data)}\n\n"

# 【流式】工具调用块 (升级以支持并行)
def format_openai_tool_call_chunks(tool_calls: list, model: str, request_id: str):
    chunks = []
    for i, tool_call in enumerate(tool_calls):
        chunk_data = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": None,
                    "tool_calls": [{
                        "index": i, # <-- 关键：每个调用有自己的索引
                        "id": tool_call['id'],
                        "type": "function",
                        "function": { "name": tool_call['function']['name'], "arguments": "" }
                    }]
                },
                "finish_reason": None
            }]
        }
        # 发送函数名
        chunks.append(f"data: {json.dumps(chunk_data)}\n\n")

        # 发送参数
        chunk_data["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = tool_call['function']['arguments']
        chunks.append(f"data: {json.dumps(chunk_data)}\n\n")

    return "".join(chunks)

# 【流式】结束块
def format_openai_finish_chunk(model: str, request_id: str, finish_reason: str = "stop"):
    chunk_data = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]}
    return f"data: {json.dumps(chunk_data)}\n\n"

# 【非流式】响应格式化函数 (升级以支持并行)
def format_openai_non_stream_response(content: str, tool_calls: list, model: str, request_id: str, finish_reason: str):
    message = {"role": "assistant"}
    if tool_calls:
        message["tool_calls"] = tool_calls
    else:
        message["content"] = content

    response_data = {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }
    # 【【【新日志】】】
    print("\n--- 📦 [Non-Stream] 最终响应体 ---")
    print(json.dumps(response_data, indent=2, ensure_ascii=False))
    print("----------------------------------\n")
    return response_data

# --- Google 响应解析与任务处理 (核心升级) ---

# v5 解析器 (保持不变)
def _extract_value(value_wrapper):
    current_payload = value_wrapper
    while isinstance(current_payload, list):
        non_null_items = [item for item in current_payload if item is not None]
        if len(non_null_items) == 1: current_payload = non_null_items[0]
        else: break
    if not isinstance(current_payload, list): return current_payload
    if not current_payload: return []
    first_item = current_payload[0]
    if isinstance(first_item, list) and len(first_item) == 2 and isinstance(first_item[0], str):
        return convert_google_args_to_dict(current_payload)
    else:
        return [_extract_value(item) for item in current_payload]

def convert_google_args_to_dict(args_list: list) -> dict:
    if not isinstance(args_list, list): return {}
    params = {}
    for item in args_list:
        if isinstance(item, list) and len(item) == 2 and isinstance(item[0], str):
            key, value_wrapper = item[0], item[1]
            params[key] = _extract_value(value_wrapper)
    return params

# 【【【核心升级：解析所有函数调用】】】
def parse_final_buffer_for_tool_calls(buffer: str):
    """
    在流结束后，解析整个缓冲区以提取【所有】函数调用。
    返回一个函数调用对象的列表，如果找不到则返回空列表。
    """
    all_tool_calls = []
    try:
        clean_buffer = buffer.strip().lstrip(',')
        full_json_str = f"[{clean_buffer}]"
        all_chunks = json.loads(full_json_str)
        
        # 递归查找所有函数调用结构体: `["function_name", [[args]]]`
        def find_all_calls_recursive(data):
            found_calls = []
            # 检查当前节点是否是函数调用
            if (isinstance(data, list) and len(data) > 0 and isinstance(data[0], str) and data[0] and
                    len(data) > 1 and isinstance(data[1], list) and len(data[1]) > 0 and isinstance(data[1][0], list)):
                return [data] # 找到了一个，返回一个包含它的列表
            
            # 如果不是，递归搜索子节点
            if isinstance(data, list):
                for item in data:
                    found_calls.extend(find_all_calls_recursive(item))
            return found_calls

        for chunk in reversed(all_chunks):
            if not isinstance(chunk, list): continue
            if "Model generated function call(s)." in str(chunk):
                # 从这个标志性块开始递归搜索
                raw_calls = find_all_calls_recursive(chunk)
                for call_data in raw_calls:
                    function_name = call_data[0]
                    arguments_dict = convert_google_args_to_dict(call_data[1][0])
                    all_tool_calls.append({
                        "id": f"call_{uuid.uuid4()}",
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": json.dumps(arguments_dict, ensure_ascii=False)
                        }
                    })
                # 找到标志块后就处理并退出，避免重复解析
                if all_tool_calls:
                    break
    except Exception as e:
        print(f"🚨 [Tool Call Parser Error] 解析最终缓冲区时发生未知错误: {type(e).__name__}: {e}")
    
    return all_tool_calls

def _internal_task_processor(task_id: str):
    # (此函数无需更改)
    start_time = time.time()
    while time.time() - start_time < 120:
        try:
            res = requests.get(f"{INTERNAL_SERVER_URL}/get_chunk/{task_id}", timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data['status'] == 'ok': yield data.get('chunk')
                elif data['status'] == 'done':
                    yield END_OF_STREAM_SIGNAL
                    return
            time.sleep(0.05)
        except requests.exceptions.RequestException: time.sleep(1)
    yield END_OF_STREAM_SIGNAL

def _update_conversation_state(request_base, new_messages: list):
    """
    通用状态更新函数。
    - request_base: 不包含新消息的基础请求。
    - new_messages: 一个包含 'user'/'tool' 和 'assistant' 消息的列表。
    """
    global LAST_CONVERSATION_STATE
    new_state = request_base.copy()
    new_state["messages"].extend(new_messages)
    LAST_CONVERSATION_STATE = new_state
    print(f"✅ [Cache] 会话状态已更新，新增 {len(new_messages)} 条消息。")

# --- 主处理逻辑 (升级以支持并行) ---

def stream_and_update_state(task_id: str, request_base: dict, user_or_tool_message: dict):
    model = request_base.get("model", "gemini-custom")
    request_id = f"chatcmpl-{uuid.uuid4()}"
    text_pattern = re.compile(r'\[\s*null\s*,\s*\"((?:\\.|[^\"\\])*)\"')
    full_raw_response_buffer = ""
    full_ai_response_text = ""

    print("... 🟢 [Stream Mode] 开始实时传输 ...")
    for chunk_content in _internal_task_processor(task_id):
        if chunk_content == END_OF_STREAM_SIGNAL: break
        full_raw_response_buffer += chunk_content
        match = text_pattern.search(chunk_content)
        if match:
            try:
                text = json.loads(f'"{match.group(1)}"')
                if text and not text.startswith("**"):
                    full_ai_response_text += text
                    yield format_openai_chunk(text, model, request_id)
            except json.JSONDecodeError: continue

    print("... 🟡 [Stream Mode] 流结束，解析最终结果 ...")
    final_tool_calls = parse_final_buffer_for_tool_calls(full_raw_response_buffer)
    finish_reason = "stop"
    assistant_message = {"role": "assistant"}

    if final_tool_calls:
        print(f"✅ [Stream Mode] 成功解析 {len(final_tool_calls)} 个工具调用。")
        finish_reason = "tool_calls"
        assistant_message["tool_calls"] = final_tool_calls
        yield format_openai_tool_call_chunks(final_tool_calls, model, request_id)
    else:
        assistant_message["content"] = full_ai_response_text
    
    _update_conversation_state(request_base, [user_or_tool_message, assistant_message])
    yield format_openai_finish_chunk(model, request_id, finish_reason)
    yield "data: [DONE]\n\n"

def generate_non_streaming_response(task_id: str, request_base: dict, user_or_tool_message: dict):
    model = request_base.get("model", "gemini-custom")
    request_id = f"chatcmpl-{uuid.uuid4()}"
    text_pattern = re.compile(r'\[\s*null\s*,\s*\"((?:\\.|[^\"\\])*)\"')
    full_raw_response_buffer = ""
    full_ai_response_text = ""

    print("... 🟢 [Non-Stream Mode] 在后台收集所有数据 ...")
    for chunk_content in _internal_task_processor(task_id):
        if chunk_content == END_OF_STREAM_SIGNAL: break
        full_raw_response_buffer += chunk_content
        match = text_pattern.search(chunk_content)
        if match:
            try:
                text = json.loads(f'"{match.group(1)}"')
                if text and not text.startswith("**"):
                    full_ai_response_text += text
            except json.JSONDecodeError: continue
    
    print("... 🟡 [Non-Stream Mode] 收集完成，解析最终结果 ...")
    final_tool_calls = parse_final_buffer_for_tool_calls(full_raw_response_buffer)
    finish_reason = "stop"
    assistant_message = {"role": "assistant"}

    if final_tool_calls:
        print(f"✅ [Non-Stream Mode] 成功解析 {len(final_tool_calls)} 个工具调用。")
        finish_reason = "tool_calls"
        assistant_message["tool_calls"] = final_tool_calls
    else:
        assistant_message["content"] = full_ai_response_text
    
    _update_conversation_state(request_base, [user_or_tool_message, assistant_message])
    
    final_json_response = format_openai_non_stream_response(
        full_ai_response_text,
        final_tool_calls,
        model,
        request_id,
        finish_reason
    )
    return final_json_response

# --- 服务器路由与主逻辑 (保持不变) ---
def check_internal_server():
    print("...正在检查内部服务器状态...")
    try:
        response = requests.get(INTERNAL_SERVER_URL, timeout=3)
        if response.status_code == 200:
            print(f"✅ 内部服务器 (在 {INTERNAL_SERVER_URL}) 连接成功！")
            return True
    except requests.exceptions.RequestException:
        print("\n" + "!"*60); print("!! 致命错误：无法连接到内部服务器！"); print(f"!! 请确保 `local_history_server.py` 已经启动并且正在 {INTERNAL_SERVER_URL} 上运行。"); print("!"*60); return False

def _normalize_message_content(message: dict) -> dict:
    content = message.get("content");
    if isinstance(content, list):
        message["content"] = "\n\n".join([p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"])
    return message

def _inject_history(job_payload: dict, wait_time: int = 15):
    try:
        requests.post(f"{INTERNAL_SERVER_URL}/submit_injection_job", json=job_payload).raise_for_status()
        time.sleep(wait_time); return True
    except requests.exceptions.RequestException: return False

def _submit_prompt(prompt: str):
    try:
        response = requests.post(f"{INTERNAL_SERVER_URL}/submit_prompt", json={"prompt": prompt})
        response.raise_for_status(); return response.json()['task_id']
    except requests.exceptions.RequestException: return None

def _submit_tool_result(result: str):
    """
    为工具函数返回结果创建一个新的任务，并将其提交到内部服务器。
    返回一个新的 task_id 用于跟踪 AI 的后续响应。
    """
    try:
        new_task_id = str(uuid.uuid4())
        payload = {"task_id": new_task_id, "result": result}
        response = requests.post(f"{INTERNAL_SERVER_URL}/submit_tool_result", json=payload)
        response.raise_for_status()
        print(f"✅ [API Gateway] 已为工具返回结果创建并提交新任务 (ID: {new_task_id[:8]})。")
        return new_task_id
    except requests.exceptions.RequestException as e:
        print(f"🚨 [API Gateway] 提交工具结果失败: {e}")
        return None


@app.route('/reset_state', methods=['POST'])
def reset_state():
    global LAST_CONVERSATION_STATE; LAST_CONVERSATION_STATE = None
    print("🔄 [Cache] 会话缓存已被手动重置。")
    return jsonify({"status": "success", "message": "Conversation cache has been reset."})

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    if request.method == 'OPTIONS': return '', 200
    global LAST_CONVERSATION_STATE
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 接收到新的 /v1/chat/completions 请求...")
    request_data = request.json
    try:
        messages = [_normalize_message_content(msg) for msg in request_data.get("messages", [])]
        request_data["messages"] = messages
    except Exception as e: return jsonify({"error": f"处理消息内容时失败: {e}"}), 400
    if not messages: return jsonify({"error": "'messages' 列表不能为空。"}), 400

    use_stream = request_data.get('stream', False)
    print(f"模式检测: stream={use_stream}")
    is_continuation = False
    if LAST_CONVERSATION_STATE:
        cached_messages, new_messages_base = LAST_CONVERSATION_STATE.get("messages", []), messages[:-1]
        # 检查是否是连续对话（用户或工具）
        if json.dumps(cached_messages, sort_keys=True) == json.dumps(new_messages_base, sort_keys=True):
            last_message_role = messages[-1].get("role")
            if last_message_role in ["user", "tool"]:
                 is_continuation = True

    task_id, last_message, request_base_for_update = None, None, None
    
    if is_continuation:
        last_message = messages[-1]
        request_base_for_update = request_data.copy()
        request_base_for_update["messages"] = messages[:-1] # 更新状态时只用基础部分

        if last_message.get("role") == "user":
            print("⚡️ [Fast Path] 检测到连续【用户对话】，跳过页面刷新。")
            task_id = _submit_prompt(last_message.get("content"))
            if not task_id:
                LAST_CONVERSATION_STATE = None
                return jsonify({"error": "快速通道提交Prompt失败"}), 500
        
        elif last_message.get("role") == "tool":
            print("️️️⚡️ [Fast Path] 检测到【工具结果返回】，准备提交。")
            tool_result_content = last_message.get("content", "")
            task_id = _submit_tool_result(tool_result_content)
            if not task_id:
                LAST_CONVERSATION_STATE = None
                return jsonify({"error": "提交工具结果失败"}), 500

    else: # 新对话或状态不一致
        print("🔄 [Full Injection] 检测到新对话或状态不一致，执行完整页面注入。")
        LAST_CONVERSATION_STATE = None
        injection_payload = request_data.copy()
        last_message = messages[-1] if messages else None

        if last_message and last_message.get("role") == "user":
            injection_payload["messages"] = messages[:-1]
        else:
            last_message = None

        request_base_for_update = injection_payload
        
        if not _inject_history(injection_payload):
            return jsonify({"error": "注入历史记录失败。"}), 500
        
        if last_message:
            task_id = _submit_prompt(last_message.get("content"))
        else:
            _update_conversation_state(request_base_for_update, [])
            model = request_data.get("model", "gemini-custom")
            req_id = f"chatcmpl-{uuid.uuid4()}"
            if use_stream:
                return Response(f"{format_openai_finish_chunk(model, req_id, 'stop')}data: [DONE]\n\n", mimetype='text/event-stream')
            else:
                return jsonify(format_openai_non_stream_response("", [], model, req_id, "stop"))

    if not task_id:
        return jsonify({"error": "未能获取任务ID"}), 500

    if use_stream:
        return Response(stream_and_update_state(task_id, request_base_for_update, last_message), mimetype='text/event-stream')
    else:
        return jsonify(generate_non_streaming_response(task_id, request_base_for_update, last_message))

if __name__ == "__main__":
    if not check_internal_server(): sys.exit(1)
    print("="*60); print("  OpenAI 兼容 API 网关 v5.1 (Robust Tool Handling)"); print("="*60)
    print("  ✨ 新功能: 支持通过 'role: tool' 消息返回函数执行结果。")
    print("  ✨ 修复: 确保为工具返回的响应流正确初始化任务。")
    print("\n  运行指南:"); print("  1. ✅ `local_history_server.py` 已成功连接。"); print("  2. ✅ 确保浏览器和油猴脚本已就绪。"); print(f"  3. 🚀 本 API 服务器正在 http://127.0.0.1:{PUBLIC_PORT} 上运行。"); print("="*60)
    app.run(host='0.0.0.0', port=PUBLIC_PORT, threaded=True)