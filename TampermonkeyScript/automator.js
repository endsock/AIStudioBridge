// ==UserScript==
// @name         Google AI Studio Automator (v6.4 - The Signature Detective)
// @namespace    http://tampermonkey.net/
// @version      6.4
// @description  Implements highly specific end-of-stream detection by looking for the unique final ID signature block, preventing premature termination on intermediate metadata.
// @author       You & AI Assistant
// @match        https://aistudio.google.com/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=google.com
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      alkalimakersuite-pa.clients6.google.com
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // --- 配置 & 常量 ---
    const SCRIPT_PREFIX = 'aistudio_automator_';
    console.log(`🤖 AI Studio Automator v6.4 (The Signature Detective) 已启动！`);

    const LOCAL_SERVER_URL = "http://127.0.0.1:5101";
    const POLLING_INTERVAL = 3000;
    const INPUT_SELECTORS = [
        'textarea[aria-label="Start typing a prompt"]',
        'textarea[aria-label="Type something or tab to choose an example prompt"]'
    ];
    const SUBMIT_BUTTON_SELECTOR = 'run-button button';
    const AUTOMATION_READY_KEY = 'AUTOMATION_READY';
    const END_OF_STREAM_SIGNAL = "__END_OF_STREAM__";

    // --- 【【【核心修复：更精确的结束签名】】】 ---
    // 这个正则表达式现在只匹配那个独一无二的、包含会话ID的最终块结构。
    // 它寻找 `[null,null,null,["...` 这个永远不会在中间出现的模式。
    const FINAL_BLOCK_SIGNATURE = /\[\s*null\s*,\s*null\s*,\s*null\s*,\s*\[\s*"/;


    // --- 状态变量 ---
    let currentTask = null;
    const TAB_ID = `${Date.now()}-${Math.random()}`;
    let isMaster = false;
    let mainLoopInterval = null;
    let isRequesting = false;
    let interceptorActive = false;

    // --- 【【【核心升级：网络拦截器 v2.2 - 签名检测版】】】 ---
    const originalXhrOpen = window.XMLHttpRequest.prototype.open;
    const originalXhrSend = window.XMLHttpRequest.prototype.send;
    const TARGET_URL_PART = "MakerSuiteService/GenerateContent";

    function sendStreamChunk(chunk) {
        if (!currentTask || !chunk) return;
        GM_xmlhttpRequest({
            method: "POST",
            url: `${LOCAL_SERVER_URL}/stream_chunk`,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify({ task_id: currentTask.task_id, chunk: chunk }),
            onerror: (err) => { console.error("...[Stream] 块发送失败:", err); }
        });
    }

    function installNetworkInterceptor(resolve, reject) {
        if (interceptorActive) { return; }
        const overallTimeout = setTimeout(() => {
            restoreNetworkInterceptor();
            reject("网络拦截超时（60秒），未捕获到目标请求。");
        }, 60000);

        interceptorActive = true;
        window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            this._url = url;
            return originalXhrOpen.apply(this, [method, url, ...rest]);
        };
        window.XMLHttpRequest.prototype.send = function(...args) {
            if (this._url && this._url.toString().includes(TARGET_URL_PART)) {
                console.log(`...🎯 [XHR Stream] 拦截到目标请求，准备接收流式数据...`);
                clearTimeout(overallTimeout);

                let lastSentLength = 0;
                let fullResponseText = "";
                let streamEnded = false;
                let finalizationTimer = null; // 用于超时保险

                const finalizeStream = () => {
                    if (streamEnded) return;
                    streamEnded = true;
                    console.log('...[Stream] 判定流已结束。');
                    clearTimeout(finalizationTimer);

                    const finalChunk = fullResponseText.slice(lastSentLength);
                    if (finalChunk) {
                        sendStreamChunk(finalChunk);
                    }
                    sendStreamChunk(END_OF_STREAM_SIGNAL);
                    resolve(fullResponseText);
                    restoreNetworkInterceptor();
                };

                this.addEventListener('progress', () => {
                    if (streamEnded) return;

                    fullResponseText = this.responseText;
                    const newChunk = fullResponseText.slice(lastSentLength);
                    if (newChunk) {
                        sendStreamChunk(newChunk);
                        lastSentLength = fullResponseText.length;

                        // 【【【关键】】】使用新的、更精确的签名来检查流是否结束
                        if (FINAL_BLOCK_SIGNATURE.test(newChunk)) {
                            console.log('...[Stream] ✅ 检测到最终 ID 签名块，确认流结束。');
                            finalizeStream();
                        }
                    }
                });

                this.addEventListener('load', () => {
                    if (streamEnded) return;
                    console.log('...[Stream] "load" 事件触发，启动最终确认计时器 (作为保险)。');
                    finalizationTimer = setTimeout(finalizeStream, 1500); // 延长一点保险时间
                });

                this.addEventListener('error', (e) => {
                    console.error("...[Stream] XHR 请求出错:", e);
                    if (!streamEnded) finalizeStream();
                    reject("XHR 请求出错");
                });
                this.addEventListener('abort', () => {
                    console.log("...[Stream] XHR 请求被中止。");
                    if (!streamEnded) finalizeStream();
                    reject("XHR 请求被中止");
                });
            }
            return originalXhrSend.apply(this, args);
        };
    }

    function restoreNetworkInterceptor() {
        if (interceptorActive) {
            window.XMLHttpRequest.prototype.open = originalXhrOpen;
            window.XMLHttpRequest.prototype.send = originalXhrSend;
            interceptorActive = false;
            console.log("...[Automator] XMLHttpRequest 拦截器已恢复。");
        }
    }

    // --- 任务处理与服务器通信 (升级以处理工具结果) ---
    async function handlePromptTask(promptText) {
        console.log(`...[Automator] 开始处理新【对话】: "${promptText}"`);
        if (interceptorActive) restoreNetworkInterceptor();

        const interceptPromise = new Promise((resolve, reject) => {
            installNetworkInterceptor(resolve, reject);
        });

        const inputArea = await waitForElement(INPUT_SELECTORS);
        if (!inputArea) {
            restoreNetworkInterceptor();
            reportTaskResult("failed", "找不到任何一个有效的主输入框。");
            return;
        }
        inputArea.value = promptText;
        inputArea.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await new Promise(r => setTimeout(r, 300));

        const submitButton = document.querySelector(SUBMIT_BUTTON_SELECTOR);
        if (!submitButton || submitButton.disabled) {
            restoreNetworkInterceptor();
            reportTaskResult("failed", "提交按钮未激活。");
            return;
        }
        submitButton.click();
        console.log("...[Automator] 主提交按钮已点击，等待网络响应...");

        try {
            const fullRawContent = await interceptPromise;
            reportTaskResult("completed", fullRawContent);
        } catch (error) {
            reportTaskResult("failed", error.toString());
        }
    }

    async function handleToolResultTask(resultText) {
        console.log(`...[Automator] 开始处理【工具返回结果】...`);
        if (interceptorActive) restoreNetworkInterceptor();

        const interceptPromise = new Promise((resolve, reject) => {
            installNetworkInterceptor(resolve, reject);
        });

        // 1. 找到最后一个函数调用块内的响应文本域
        const toolResponseTextareas = document.querySelectorAll('textarea[placeholder="Enter function response"]');
        if (toolResponseTextareas.length === 0) {
            restoreNetworkInterceptor();
            reportTaskResult("failed", "找不到任何工具函数响应的输入框。");
            return;
        }
        const lastTextarea = toolResponseTextareas[toolResponseTextareas.length - 1];

        // 2. 填入结果
        lastTextarea.value = resultText;
        lastTextarea.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await new Promise(r => setTimeout(r, 300));

        // 3. 找到与该文本域关联的提交按钮并点击
        const submitButton = lastTextarea.closest('form')?.querySelector('button[type="submit"]');
        if (!submitButton || submitButton.disabled) {
            restoreNetworkInterceptor();
            reportTaskResult("failed", "工具函数响应的提交按钮未激活。");
            return;
        }
        submitButton.click();
        console.log("...[Automator] 工具结果提交按钮已点击，等待网络响应...");

        try {
            const fullRawContent = await interceptPromise;
            reportTaskResult("completed", fullRawContent);
        } catch (error) {
            reportTaskResult("failed", error.toString());
        }
    }


    function pollForJobs() {
        if (currentTask || isRequesting) return;
        isRequesting = true;

        // 优先检查工具返回任务
        GM_xmlhttpRequest({
            method: "GET",
            url: `${LOCAL_SERVER_URL}/get_tool_result_job`,
            onload: (res) => {
                try {
                    const data = JSON.parse(res.responseText);
                    if (data.status === 'success' && data.job) {
                        currentTask = data.job;
                        handleToolResultTask(currentTask.result);
                        isRequesting = false; // 任务已找到，可以结束请求链
                    } else {
                        // 如果没有工具任务，则检查普通对话任务
                        pollForPromptJob();
                    }
                } catch (e) {
                    pollForPromptJob(); // 解析失败，继续检查
                }
            },
            onerror: (err) => {
                console.error("❌ Automator: 工具任务轮询连接失败:", err);
                pollForPromptJob(); // 连接失败，继续检查
            }
        });
    }

    function pollForPromptJob() {
        // 这个函数现在是 pollForJobs 的一部分，所以不需要重复设置 isRequesting
        GM_xmlhttpRequest({
            method: "GET",
            url: `${LOCAL_SERVER_URL}/get_prompt_job`,
            onload: (res) => {
                try {
                    const data = JSON.parse(res.responseText);
                    if (data.status === 'success' && data.job) {
                        currentTask = data.job;
                        handlePromptTask(currentTask.prompt);
                    }
                } catch (e) {}
            },
            onerror: (err) => console.error("❌ Automator: 对话任务轮询连接失败:", err),
            onloadend: () => { isRequesting = false; } // 无论结果如何，结束请求链
        });
    }

    function reportTaskResult(status, content = "") {
        if (!currentTask) return;
        const taskIdToReport = currentTask.task_id;
        console.log(`...[Automator] 报告任务 #${taskIdToReport.slice(-8)} 最终状态: ${status}`);
        isRequesting = true;
        GM_xmlhttpRequest({
            method: "POST",
            url: `${LOCAL_SERVER_URL}/report_result`,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify({
                task_id: taskIdToReport,
                status: status,
                content: content
            }),
            onload: () => {
                console.log(`✔️ Automator: 任务 #${taskIdToReport.slice(-8)} 最终状态报告成功。`);
                if (currentTask && currentTask.task_id === taskIdToReport) {
                    currentTask = null;
                }
            },
            onerror: () => console.error(`❌ Automator: 报告任务 #${taskIdToReport.slice(-8)} 结果失败`),
            onloadend: () => {
                isRequesting = false;
            }
        });
    }

    // --- 启动与主从选举逻辑 (无变化) ---
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
            console.log(`👑 [Tab ${TAB_ID.slice(-4)}] 我现在是主标签页!`);
            isMaster = true;
            updateHeartbeat();
            const checkReadyInterval = setInterval(() => {
                if (sessionStorage.getItem(AUTOMATION_READY_KEY) === 'true') {
                    console.log('✅ Automator: 检测到注入完成信标，启动对话轮询主循环！');
                    clearInterval(checkReadyInterval);
                    sessionStorage.removeItem(AUTOMATION_READY_KEY);
                    startMainLoop();
                } else {
                    console.log('...[Automator] 等待 History Forger 完成注入...');
                }
            }, 1000);
        }
    }

    function becomeSlave() {
        if (isMaster) {
            console.log(`👤 [Tab ${TAB_ID.slice(-4)}] 我现在是“从”标签页，停止轮询。`);
            isMaster = false;
            stopMainLoop();
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

    function startMainLoop() {
        if (mainLoopInterval) clearInterval(mainLoopInterval);
        pollForJobs();
        mainLoopInterval = setInterval(pollForJobs, POLLING_INTERVAL);
    }

    function stopMainLoop() {
        if (mainLoopInterval) {
            clearInterval(mainLoopInterval);
            mainLoopInterval = null;
        }
    }

    async function waitForElement(selectors, timeout = 10000) {
        return new Promise(resolve => {
            const selectorArray = Array.isArray(selectors) ? selectors : [selectors];
            let intervalId = null;
            const timer = setTimeout(() => {
                clearInterval(intervalId);
                console.error(`waitForElement 超时: 未在 ${timeout}ms 内找到任何选择器:`, selectorArray);
                resolve(null);
            }, timeout);

            intervalId = setInterval(() => {
                for (const selector of selectorArray) {
                    const el = document.querySelector(selector);
                    if (el && el.offsetParent !== null) {
                        clearInterval(intervalId);
                        clearTimeout(timer);
                        resolve(el);
                        return;
                    }
                }
            }, 200);
        });
    }

    window.addEventListener('load', () => {
        setTimeout(() => {
            manageMasterRole();
            setInterval(manageMasterRole, ELECTION_INTERVAL);
        }, 3000);
    });

})();