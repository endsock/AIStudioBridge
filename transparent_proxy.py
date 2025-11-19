import requests
import uuid
import json
import os
from flask import Flask, request, Response
from flask_cors import CORS

app = Flask(__name__)

# 配置目标地址
# 配置目标地址
TARGET_URL = "https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal:streamGenerateContent?alt=sse"

GLOBAL_ACCESS_TOKEN = None

def transform_chunk_data(original_chunk):
    """转换SSE格式的chunk为标准JSON格式"""
    try:
        # 解码bytes为字符串
        chunk_str = original_chunk.decode('utf-8').strip()

        # 如果以data:开头，去掉data:前缀
        if chunk_str.startswith('data: '):
            json_str = chunk_str[6:]  # 去掉'data: '
        elif chunk_str.startswith('data:'):
            json_str = chunk_str[5:]  # 去掉'data:'
        else:
            return original_chunk  # 不是SSE格式，直接返回

        # 解析JSON
        data = json.loads(json_str)

        # 检查是否包含response字段
        if 'response' in data:
            response_data = data['response']

            # 转换为JSON字符串并编码回bytes
            return ("data: " + json.dumps(response_data) + '\n\n').encode('utf-8')
        else:
            # 没有response字段，直接去掉data:前缀返回
            return ("data: " + json_str + '\n\n').encode('utf-8')

    except Exception as e:
        print(f"⚠️ 数据转换失败: {e}, 返回原始数据")
        return original_chunk

def refresh_access_token():
    print("🔄 Attempting to refresh OAuth2 token...")
    url = "https://oauth2.googleapis.com/token"
    headers = {
        "Host": "oauth2.googleapis.com",
        "User-Agent": "Go-http-client/1.1"
    }
    
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'oauth_config.json')
        with open(config_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"🚨 Failed to load oauth_config.json: {e}")
        return None
    
    try:
        resp = requests.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            token_data = resp.json()
            access_token = token_data.get("access_token")
            print(f"✅ Token refreshed successfully. New token starts with: {access_token[:10]}...")
            print(access_token)
            return access_token
        else:
            print(f"🚨 Failed to refresh token: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"🚨 Exception during token refresh: {e}")
        return None

@app.route('/v1beta/models/<model>:streamGenerateContent', methods=['POST', 'OPTIONS'])
def proxy_stream_generate_content(model):
    global GLOBAL_ACCESS_TOKEN

    if request.method == 'OPTIONS':
        return '', 200

    # 1. 获取原始请求的 Headers (排除 Host 和 Content-Length 以避免冲突)
    headers = {}
    headers["Host"] = "daily-cloudcode-pa.sandbox.googleapis.com"
    headers["User-Agent"] = "antigravity/1.11.3 windows/amd64"
    headers["Content-Type"] = "application/json"
    # headers["Accept-Encoding"] = "gzip"

    # 使用全局 Token
    if GLOBAL_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {GLOBAL_ACCESS_TOKEN}"
    
    # 2. 获取原始请求的 JSON 数据
    try:
        post_data = {}
        post_data["project"] = "poised-vortex-8rl9f"
        post_data["requestId"] = f"agent-{uuid.uuid4()}"
        if model == "super-glm-think":
            model = "claude-sonnet-4-5-thinking"
        elif model == "super-glm":
            model = "claude-sonnet-4-5"
        post_data["model"] = model
        json_data = request.get_json()
        if json_data is None:
             return f"request JSON is None", 400
        post_data["request"] = json_data
            
        if "generationConfig" not in post_data["request"]:
            post_data["request"]["generationConfig"] = {}
        
        post_data["request"]["generationConfig"]["thinkingConfig"] = {
            "includeThoughts": True
        }
    except Exception as e:
        return f"Invalid JSON: {e}", 400

    # 3. 定义流式生成器
    def generate():
        try:
            # 发起请求到目标地址，开启 stream=True
            # verify=False 用于忽略 SSL 证书验证（针对 IP 地址访问通常需要）
            resp = requests.post(TARGET_URL, headers=headers, json=post_data, stream=True, verify=False)

            # 检查是否需要刷新 Token (401 Unauthorized)
            if resp.status_code == 401:
                print("⚠️ Received 401 Unauthorized. Trying to refresh token...")
                resp.close() # 关闭旧连接
                
                new_token = refresh_access_token()
                if new_token:
                    global GLOBAL_ACCESS_TOKEN
                    GLOBAL_ACCESS_TOKEN = new_token
                    headers["Authorization"] = f"Bearer {new_token}"
                    print("🔄 Retrying request with new token...")
                    resp = requests.post(TARGET_URL, headers=headers, json=post_data, stream=True, verify=False)
                else:
                    yield "Failed to refresh OAuth2 token."
                    return

            with resp:
                # 透传状态码 (如果目标返回非 200，这里也可以处理，但流式通常假设 200)
                # 注意：Flask 的 Response 生成器无法在开始生成后更改状态码，
                # 所以如果 resp.status_code != 200，最好先检查一下。
                if resp.status_code != 200:
                    yield f"Error from upstream: {resp.status_code} - {resp.text}"
                    return

                # 逐块读取并返回
                for chunk in resp.iter_content(chunk_size=40960000):
                    if chunk:
                        # 应用数据格式转换
                        transformed_chunk = transform_chunk_data(chunk)
                        yield transformed_chunk
        except Exception as e:
            yield f"Proxy Error: {str(e)}"

    # 4. 返回流式响应
    # mimetype 设为 'application/json' 或者 'text/event-stream'，取决于上游返回什么。
    # 既然是透明代理，最好透传 Content-Type，或者默认设为流式常用类型。
    # 这里参考 openai_compatible_server.py 使用 Response 对象
    return Response(generate(), mimetype='text/event-stream')

@app.route('/v1beta/models/<model>:generateContent', methods=['POST', 'OPTIONS'])
def proxy_generate_content(model):
    global GLOBAL_ACCESS_TOKEN

    if request.method == 'OPTIONS':
        return '', 200

    # 1. 获取原始请求的 Headers (排除 Host 和 Content-Length 以避免冲突)
    headers = {}
    headers["Host"] = "daily-cloudcode-pa.sandbox.googleapis.com"
    headers["User-Agent"] = "antigravity/1.11.3 windows/amd64"
    headers["Content-Type"] = "application/json"

    # 使用全局 Token
    if GLOBAL_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {GLOBAL_ACCESS_TOKEN}"

    # 2. 获取原始请求的 JSON 数据
    try:
        post_data = {}
        post_data["project"] = "poised-vortex-8rl9f"
        post_data["requestId"] = f"agent-{uuid.uuid4()}"
        if model == "super-glm-think":
            model = "claude-sonnet-4-5-thinking"
        elif model == "super-glm":
            model = "claude-sonnet-4-5"
        post_data["model"] = model
        json_data = request.get_json()
        if json_data is None:
             return "request JSON is None", 400
        post_data["request"] = json_data

        if "generationConfig" not in post_data["request"]:
            post_data["request"]["generationConfig"] = {}

        post_data["request"]["generationConfig"]["thinkingConfig"] = {
            "includeThoughts": True
        }
    except Exception as e:
        return f"Invalid JSON: {e}", 400

    # 3. 发起非流式请求
    try:
        # 发起请求到目标地址，非流式模式
        # verify=False 用于忽略 SSL 证书验证（针对 IP 地址访问通常需要）
        resp = requests.post(TARGET_URL.replace(':streamGenerateContent?alt=sse', ':generateContent'),
                           headers=headers, json=post_data, stream=False, verify=False)

        # 检查是否需要刷新 Token (401 Unauthorized)
        if resp.status_code == 401:
            print("⚠️ Received 401 Unauthorized. Trying to refresh token...")

            new_token = refresh_access_token()
            if new_token:
                GLOBAL_ACCESS_TOKEN = new_token
                headers["Authorization"] = f"Bearer {new_token}"
                print("🔄 Retrying request with new token...")
                resp = requests.post(TARGET_URL.replace(':streamGenerateContent?alt=sse', ':generateContent'),
                                   headers=headers, json=post_data, stream=False, verify=False)
            else:
                return "Failed to refresh OAuth2 token.", 401

        # 检查响应状态码
        if resp.status_code != 200:
            return f"Error from upstream: {resp.status_code} - {resp.text}", resp.status_code

        # 返回非流式响应
        # 透传响应头中的 Content-Type
        response_headers = {}
        if 'Content-Type' in resp.headers:
            response_headers['Content-Type'] = resp.headers['Content-Type']

        return resp.content, resp.status_code, response_headers.items()

    except Exception as e:
        return f"Proxy Error: {str(e)}", 500

if __name__ == "__main__":
    print(f"Starting Transparent Proxy on port 5105...")
    print(f"Target URL: {TARGET_URL}")
    
    # 启动时获取 Token
    print("🚀 Fetching initial access token...")
    GLOBAL_ACCESS_TOKEN = refresh_access_token()
    
    app.run(host='0.0.0.0', port=5105, threaded=True)
