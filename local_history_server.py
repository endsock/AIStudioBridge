# local_history_server.py

from flask import Flask, request, jsonify
from queue import Queue, Empty
import logging
import uuid
import threading

# --- 配置 ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)

# --- 数据存储 ---
INJECTION_JOBS = Queue()
PROMPT_JOBS = Queue()
TOOL_RESULT_JOBS = Queue()
MODEL_FETCH_JOBS = Queue() # 【新】为获取模型列表创建的队列
# RESULTS 现在为每个任务存储一个包含状态和流数据队列的字典
RESULTS = {}
# 【新】用于缓存从油猴脚本获取的模型数据
REPORTED_MODELS_CACHE = {
    "data": None,
    "timestamp": 0,
    "event": threading.Event() # 用于通知等待方数据已到达
}


# --- API 端点 ---

@app.route('/')
def index():
    return "历史编辑代理服务器 v6.0 (Model Fetcher Ready) 正在运行。"

# --- 注入 API (无变化) ---
@app.route('/submit_injection_job', methods=['POST'])
def submit_injection_job():
    job_data = request.json
    INJECTION_JOBS.put(job_data)
    print(f"✅ 已接收到新的【注入任务】。注入队列现有任务: {INJECTION_JOBS.qsize()}。")
    return jsonify({"status": "success", "message": "Injection job submitted"}), 200

@app.route('/get_injection_job', methods=['GET'])
def get_injection_job():
    try:
        job = INJECTION_JOBS.get_nowait()
        print(f"🚀 History Forger 已取走注入任务。队列剩余: {INJECTION_JOBS.qsize()}。")
        return jsonify({"status": "success", "job": job}), 200
    except Empty:
        return jsonify({"status": "empty"}), 200

# --- 交互式对话 API (升级以支持流式传输) ---

@app.route('/submit_prompt', methods=['POST'])
def submit_prompt():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"status": "error", "message": "需要 'prompt' 字段。"}), 400
    
    task_id = str(uuid.uuid4())
    job = {"task_id": task_id, "prompt": data['prompt']}
    PROMPT_JOBS.put(job)
    # 为新任务初始化结果存储，包括一个专用的流队列
    RESULTS[task_id] = {
        "status": "pending",
        "stream_queue": Queue(),
        "full_response": None
    }
    print(f"✅ 已接收到新的【对话任务】(ID: {task_id[:8]})。对话队列现有任务: {PROMPT_JOBS.qsize()}。")
    return jsonify({"status": "success", "task_id": task_id}), 200

@app.route('/get_prompt_job', methods=['GET'])
def get_prompt_job():
    try:
        job = PROMPT_JOBS.get_nowait()
        print(f"🚀 Automator 已取走对话任务 (ID: {job['task_id'][:8]})。队列剩余: {PROMPT_JOBS.qsize()}。")
        return jsonify({"status": "success", "job": job}), 200
    except Empty:
        return jsonify({"status": "empty"}), 200

# --- 【【【新】】】流式数据 API ---

@app.route('/stream_chunk', methods=['POST'])
def stream_chunk():
    """接收油猴脚本发送的流式数据块"""
    data = request.json
    task_id = data.get('task_id')
    chunk = data.get('chunk')
    
    # 【【【调试日志】】】
    print(f"\n--- 📥 [Local Server] 收到来自 Automator 的数据块 (Task ID: {task_id[:8]}) ---")
    print(chunk)
    print("--------------------------------------------------------------------")
    
    if task_id in RESULTS:
        # 将数据块（或结束信号）放入对应任务的队列中
        RESULTS[task_id]['stream_queue'].put(chunk)
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "无效的任务 ID"}), 404

@app.route('/get_chunk/<task_id>', methods=['GET'])
def get_chunk(task_id):
    """Python 客户端从此端点轮询数据块"""
    if task_id in RESULTS:
        try:
            # 非阻塞地从队列中获取数据
            chunk = RESULTS[task_id]['stream_queue'].get_nowait()
            # 【【【调试日志】】】
            print(f"\n--- 📤 [Local Server] API 网关已取走数据块 (Task ID: {task_id[:8]}) ---")
            print(chunk)
            print("------------------------------------------------------------------")
            return jsonify({"status": "ok", "chunk": chunk}), 200
        except Empty:
            # 如果队列为空，检查任务是否已完成
            if RESULTS[task_id]['status'] in ['completed', 'failed']:
                return jsonify({"status": "done"}), 200
            else:
                return jsonify({"status": "empty"}), 200
    return jsonify({"status": "not_found"}), 404
    
@app.route('/report_result', methods=['POST'])
def report_result():
    """当油猴脚本确认整个对话结束后，调用此接口来最终确定任务状态"""
    data = request.json
    task_id = data.get('task_id')
    if task_id and task_id in RESULTS:
        RESULTS[task_id]['status'] = data.get('status', 'completed')
        RESULTS[task_id]['full_response'] = data.get('content', '') # 存储最终的完整响应以供调试
        print(f"✔️ 任务 {task_id[:8]} 已完成。状态: {RESULTS[task_id]['status']}。")
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "无效的任务 ID。"}), 404

# --- 【【【新】】】工具函数结果 API ---

@app.route('/submit_tool_result', methods=['POST'])
def submit_tool_result():
    """接收来自 OpenAI 网关的工具函数执行结果，并为响应流准备好存储空间"""
    data = request.json
    if not data or 'task_id' not in data or 'result' not in data:
        return jsonify({"status": "error", "message": "需要 'task_id' 和 'result' 字段。"}), 400
    
    task_id = data['task_id']
    job = {"task_id": task_id, "result": data['result']}
    TOOL_RESULT_JOBS.put(job)

    # 【【【核心修复】】】为这个新任务初始化结果存储，否则后续的流数据将无处安放
    RESULTS[task_id] = {
        "status": "pending",
        "stream_queue": Queue(),
        "full_response": None
    }
    
    print(f"✅ 已接收到新的【工具返回任务】(ID: {task_id[:8]}) 并已为其准备好流接收队列。工具队列现有任务: {TOOL_RESULT_JOBS.qsize()}。")
    return jsonify({"status": "success"}), 200

@app.route('/get_tool_result_job', methods=['GET'])
def get_tool_result_job():
    """供 Automator 油猴脚本获取工具函数返回任务"""
    try:
        job = TOOL_RESULT_JOBS.get_nowait()
        print(f"🚀 Automator 已取走工具返回任务 (ID: {job['task_id'][:8]})。队列剩余: {TOOL_RESULT_JOBS.qsize()}。")
        return jsonify({"status": "success", "job": job}), 200
    except Empty:
        return jsonify({"status": "empty"}), 200

# --- 【【【新】】】模型获取 API ---

@app.route('/submit_model_fetch_job', methods=['POST'])
def submit_model_fetch_job():
    """由 OpenAI 网关调用，创建一个“获取模型列表”的任务"""
    if not MODEL_FETCH_JOBS.empty():
        return jsonify({"status": "success", "message": "A fetch job is already pending."}), 200
    
    task_id = str(uuid.uuid4())
    job = {"task_id": task_id, "type": "FETCH_MODELS"}
    MODEL_FETCH_JOBS.put(job)
    
    # 重置事件，以便新的请求可以等待
    REPORTED_MODELS_CACHE['event'].clear()
    REPORTED_MODELS_CACHE['data'] = None

    print(f"✅ 已接收到新的【模型获取任务】(ID: {task_id[:8]})。")
    return jsonify({"status": "success", "task_id": task_id})

@app.route('/get_model_fetch_job', methods=['GET'])
def get_model_fetch_job():
    """由 Model Fetcher 油猴脚本轮询，以检查是否有待处理的获取任务"""
    try:
        job = MODEL_FETCH_JOBS.queue[0] # 查看任务但不取出
        return jsonify({"status": "success", "job": job}), 200
    except IndexError:
        return jsonify({"status": "empty"}), 200

@app.route('/acknowledge_model_fetch_job', methods=['POST'])
def acknowledge_model_fetch_job():
    """Model Fetcher 在收到任务并准备刷新页面前调用此接口，以从队列中安全地移除任务"""
    try:
        job = MODEL_FETCH_JOBS.get_nowait()
        print(f"🚀 Model Fetcher 已确认并取走模型获取任务 (ID: {job['task_id'][:8]})。")
        return jsonify({"status": "success"}), 200
    except Empty:
        return jsonify({"status": "error", "message": "No job to acknowledge."}), 400


@app.route('/report_models', methods=['POST'])
def report_models():
    """由 Model Fetcher 油猴脚本调用，以发送拦截到的原始模型数据"""
    data = request.json
    models_json = data.get('models_json')
    if models_json:
        REPORTED_MODELS_CACHE['data'] = models_json
        REPORTED_MODELS_CACHE['timestamp'] = uuid.uuid4().int # 使用UUID确保时间戳唯一
        REPORTED_MODELS_CACHE['event'].set() # 通知所有等待方，数据已到达
        print(f"✔️ 成功接收并缓存了新的模型列表数据。")
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "需要 'models_json' 字段。"}), 400

@app.route('/get_reported_models', methods=['GET'])
def get_reported_models():
    """由 OpenAI 网关调用，以获取缓存的模型数据。如果数据不存在，将等待。"""
    # 检查是否有数据，或者等待事件被设置
    wait_result = REPORTED_MODELS_CACHE['event'].wait(timeout=60) # 等待最多60秒
    if not wait_result:
        return jsonify({"status": "error", "message": "等待模型数据超时 (60 秒)。"}), 408

    if REPORTED_MODELS_CACHE['data']:
        return jsonify({
            "status": "success",
            "data": REPORTED_MODELS_CACHE['data'],
            "timestamp": REPORTED_MODELS_CACHE['timestamp']
        }), 200
    else:
        # 这种情况理论上不应该发生，因为事件被设置了
        return jsonify({"status": "error", "message": "数据获取失败，即使事件已触发。"}), 500


if __name__ == '__main__':
    print("======================================================================")
    print("  历史编辑代理服务器 v6.0 (Model Fetcher Ready)")
    print("  - /submit_injection_job, /get_injection_job (用于初始注入)")
    print("  - /submit_prompt, /get_prompt_job (用于发起对话)")
    print("  - /submit_tool_result, /get_tool_result_job (用于返回工具结果)")
    print("  - /submit_model_fetch_job, /get_model_fetch_job (用于获取模型)")
    print("  - /stream_chunk, /get_chunk (用于流式传输)")
    print("  已在 http://127.0.0.1:5101 启动")
    print("======================================================================")
    app.run(host='0.0.0.0', port=5101, threaded=True)