// ==UserScript==
// @name         Google AI Studio Model Fetcher (XHR-Only)
// @namespace    http://tampermonkey.net/
// @version      1.1
// @description  Intercepts the ListModels XHR call to fetch available models and sends them to a local server.
// @author       AI Assistant & You
// @match        https://aistudio.google.com/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=google.com
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    const SCRIPT_PREFIX = 'aistudio_modelfetcher_';
    console.log(`🤖 AI Studio Model Fetcher v1.1 (XHR-Only) 已启动！`);

    const LOCAL_SERVER_URL = "http://127.0.0.1:5101";
    const TARGET_URL_PART = "MakerSuiteService/ListModels";
    const POLLING_INTERVAL = 5000;

    let isPolling = false;
    let isMaster = false;
    const TAB_ID = `${Date.now()}-${Math.random()}`;

    // --- 网络拦截器 (XHR-Only) ---

    // 数据处理函数
    function processAndSendData(body) {
        if (!body) return;
        console.log('...[Model Fetcher] 成功获取 ListModels 响应体。');
        try {
            // 响应体可能以 `)]}'` 开头，需要清理
            const cleanBody = body.substring(body.indexOf('['));
            GM_xmlhttpRequest({
                method: "POST",
                url: `${LOCAL_SERVER_URL}/report_models`,
                headers: { "Content-Type": "application/json" },
                data: JSON.stringify({ models_json: cleanBody }),
                onload: () => console.log('...[Model Fetcher] ✅ 模型数据已成功发送到本地服务器。'),
                onerror: (err) => console.error("...[Model Fetcher] ❌ 模型数据发送失败:", err)
            });
        } catch (e) {
            console.error("...[Model Fetcher] ❌ 解析或发送模型数据时出错:", e);
        }
    }

    // 拦截 XMLHttpRequest
    const originalXhrOpen = window.XMLHttpRequest.prototype.open;
    const originalXhrSend = window.XMLHttpRequest.prototype.send;
    window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this._url = url;
        return originalXhrOpen.apply(this, [method, url, ...rest]);
    };
    window.XMLHttpRequest.prototype.send = function(...args) {
        if (this._url && this._url.toString().includes(TARGET_URL_PART)) {
            console.log(`...🎯 [Model Fetcher] 通过 XHR 拦截到目标请求: ${this._url}`);
            this.addEventListener('load', () => {
                if (this.readyState === 4 && this.status === 200) {
                    processAndSendData(this.responseText);
                }
            });
        }
        return originalXhrSend.apply(this, args);
    };

    // --- 任务轮询与主从选举 ---
    function pollForModelFetchJob() {
        if (isPolling) return;
        isPolling = true;

        GM_xmlhttpRequest({
            method: "GET",
            url: `${LOCAL_SERVER_URL}/get_model_fetch_job`,
            onload: (res) => {
                try {
                    const data = JSON.parse(res.responseText);
                    if (data.status === 'success' && data.job) {
                        console.log('...[Model Fetcher] 收到获取模型列表的指令，准备刷新页面...');
                        // Acknowledge job first
                         GM_xmlhttpRequest({
                            method: "POST",
                            url: `${LOCAL_SERVER_URL}/acknowledge_model_fetch_job`,
                            headers: { "Content-Type": "application/json" },
                            data: JSON.stringify({ task_id: data.job.task_id }),
                            onload: () => {
                                // Then reload
                                window.location.reload();
                            }
                        });
                    }
                } catch (e) {
                    // No job or error, just ignore
                }
            },
            onerror: (err) => {
                // console.error("...[Model Fetcher] 轮询任务失败:", err); // Can be noisy
            },
            onloadend: () => {
                isPolling = false;
            }
        });
    }

    const MASTER_KEY = `${SCRIPT_PREFIX}master_tab`;
    const ELECTION_INTERVAL = 5000;
    const MASTER_TIMEOUT = ELECTION_INTERVAL * 2.5;

    function manageMasterRole() {
        const masterInfo = JSON.parse(localStorage.getItem(MASTER_KEY) || '{}');
        if (!masterInfo.id || (Date.now() - masterInfo.timestamp > MASTER_TIMEOUT)) {
            becomeMaster();
        } else if (masterInfo.id === TAB_ID) {
            updateHeartbeat();
        } else {
            becomeSlave();
        }
    }

    function becomeMaster() {
        if (!isMaster) {
            console.log(`👑 [Model Fetcher Tab ${TAB_ID.slice(-4)}] 我现在是主标签页!`);
            isMaster = true;
            updateHeartbeat();
            setInterval(pollForModelFetchJob, POLLING_INTERVAL);
        }
    }

    function becomeSlave() {
        if (isMaster) {
            console.log(`👤 [Model Fetcher Tab ${TAB_ID.slice(-4)}] 我现在是“从”标签页，停止轮询。`);
            isMaster = false;
            // The interval is already cleared when isMaster becomes false, but let's be explicit
            // No, the interval is not cleared automatically. We need to manage it.
            // Let's restructure.
        }
    }
    
    // Let's fix the master/slave logic to properly start/stop the interval.
    let mainLoopInterval = null;

    function becomeMasterFixed() {
        if (!isMaster) {
            console.log(`👑 [Model Fetcher Tab ${TAB_ID.slice(-4)}] 我现在是主标签页!`);
            isMaster = true;
            updateHeartbeat();
            if (mainLoopInterval) clearInterval(mainLoopInterval);
            pollForModelFetchJob(); // Poll immediately
            mainLoopInterval = setInterval(pollForModelFetchJob, POLLING_INTERVAL);
        }
    }

    function becomeSlaveFixed() {
        if (isMaster) {
            console.log(`👤 [Model Fetcher Tab ${TAB_ID.slice(-4)}] 我现在是“从”标签页，停止轮询。`);
            isMaster = false;
            if (mainLoopInterval) {
                clearInterval(mainLoopInterval);
                mainLoopInterval = null;
            }
        }
    }
    
    function manageMasterRoleFixed() {
        const masterInfo = JSON.parse(localStorage.getItem(MASTER_KEY) || '{}');
        if (!masterInfo.id || (Date.now() - masterInfo.timestamp > MASTER_TIMEOUT)) {
            becomeMasterFixed();
        } else if (masterInfo.id === TAB_ID) {
            updateHeartbeat();
        } else {
            becomeSlaveFixed();
        }
    }


    function updateHeartbeat() {
        if (isMaster) {
            localStorage.setItem(MASTER_KEY, JSON.stringify({ id: TAB_ID, timestamp: Date.now() }));
        }
    }

    window.addEventListener('beforeunload', () => {
        if (isMaster) localStorage.removeItem(MASTER_KEY);
    });

    window.addEventListener('load', () => {
        // Delay to avoid race conditions on page load
        setTimeout(() => {
            manageMasterRoleFixed();
            setInterval(manageMasterRoleFixed, ELECTION_INTERVAL);
        }, 4000); // Start slightly later than the automator script
    });

})();