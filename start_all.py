# start_all.py - 启动所有服务器

import threading
import time
import sys
import os

def run_local_history_server():
    """启动本地历史服务器"""
    print("启动本地历史服务器...")
    
    # 导入并运行 local_history_server
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from local_history_server import app as local_app
        print("======================================================================")
        print("  历史编辑代理服务器 v6.0 (Model Fetcher Ready)")
        print("  - /submit_injection_job, /get_injection_job (用于初始注入)")
        print("  - /submit_prompt, /get_prompt_job (用于发起对话)")
        print("  - /submit_tool_result, /get_tool_result_job (用于返回工具结果)")
        print("  - /submit_model_fetch_job, /get_model_fetch_job (用于获取模型)")
        print("  - /stream_chunk, /get_chunk (用于流式传输)")
        print("  已在 http://127.0.0.1:5101 启动")
        print("======================================================================")
        local_app.run(host='0.0.0.0', port=5101, threaded=True)
    except Exception as e:
        print(f"❌ 本地历史服务器启动失败: {e}")

def run_openai_server():
    """启动OpenAI兼容服务器"""
    print("启动OpenAI兼容服务器...")
    
    # 导入并运行 openai_compatible_server
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from openai_compatible_server import app as openai_app, check_internal_server, PUBLIC_PORT
        
        # 等待本地历史服务器启动
        print("等待本地历史服务器启动...")
        time.sleep(3)
        
        if not check_internal_server():
            print("❌ 无法连接到内部服务器，OpenAI服务器启动失败")
            sys.exit(1)
            
        print("="*60)
        print("  OpenAI 兼容 API 网关 v6.0 (Model Fetcher Ready)")
        print("="*60)
        print("  ✨ 新功能: 支持通过 /v1/models 动态获取模型列表。")
        print("  ✨ 新功能: 支持通过 'role: tool' 消息返回函数执行结果。")
        print("\n  运行指南:")
        print("  1. ✅ `local_history_server.py` 已成功连接。")
        print("  2. ✅ 确保浏览器和油猴脚本已就绪。")
        print(f"  3. 🚀 本 API 服务器正在 http://127.0.0.1:{PUBLIC_PORT} 上运行。")
        print("="*60)
        openai_app.run(host='0.0.0.0', port=PUBLIC_PORT, threaded=True)
    except Exception as e:
        print(f"❌ OpenAI兼容服务器启动失败: {e}")

def main():
    """主函数 - 启动两个服务器"""
    print("🚀 启动 AI Studio Bridge 所有服务...")
    print("="*60)
    
    # 创建线程
    local_thread = threading.Thread(target=run_local_history_server, daemon=True)
    openai_thread = threading.Thread(target=run_openai_server, daemon=True)
    
    try:
        # 启动本地历史服务器线程
        local_thread.start()
        print("✅ 本地历史服务器线程已启动")
        
        # 稍等片刻再启动OpenAI服务器
        time.sleep(2)
        
        # 启动OpenAI兼容服务器线程
        openai_thread.start()
        print("✅ OpenAI兼容服务器线程已启动")
        
        print("\n🎉 所有服务器已启动！")
        print("按 Ctrl+C 停止所有服务")
        
        # 保持主线程运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 接收到停止信号，正在关闭服务器...")
        print("👋 再见！")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 启动过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()