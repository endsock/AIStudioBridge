# local_history_server.py

from flask import Flask, request, jsonify
from queue import Queue, Empty
import logging
import uuid

# --- 配置 ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)

# --- 数据存储 ---
# 任务队列和结果存储现在更加复杂，以支持流式传输
INJECTION_JOBS = Queue()
PROMPT_JOBS = Queue()
# RESULTS 现在为每个任务存储一个包含状态和流数据队列的字典
# { "task_id": {"status": "pending", "stream_queue": Queue(), "full_response": None} }
RESULTS = {}

# --- API 端点 ---

@app.route('/')
def index():
    return "历史编辑代理服务器 v4.0 (Streaming Ready) 正在运行。"

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


if __name__ == '__main__':
    print("======================================================================")
    print("  历史编辑代理服务器 v4.0 (Streaming Ready)")
    print("  - /submit_injection_job, /get_injection_job (用于初始注入)")
    print("  - /submit_prompt, /get_prompt_job (用于发起对话)")
    print("  - /stream_chunk, /get_chunk (用于流式传输)")
    print("  已在 http://127.0.0.1:5101 启动")
    print("======================================================================")
    app.run(host='0.0.0.0', port=5101, threaded=True)