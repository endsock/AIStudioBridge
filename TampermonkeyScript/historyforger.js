// ==UserScript==
// @name         Google AI Studio - History Forger (v7.2 - The Index Corrector)
// @namespace    http://tampermonkey.net/
// @version      7.2
// @description  Full control over AI Studio history and settings. Supports Text, JSON Mode, and Function Calling, with a robust UI corrector.
// @author       You & AI Assistant
// @match        https://aistudio.google.com/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=google.com
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';
    console.log('🤖 AI Studio History Forger v7.1 (The Index Corrector) Loaded!');

    // --- 配置和常量 ---
    const TARGET_URL_PART = "MakerSuiteService/ResolveDriveResource";
    const LOCAL_SERVER_URL = "http://127.0.0.1:5101";
    const POLLING_INTERVAL = 2000;
    const ACTION_KEY = 'AISTUDIO_FORGE_ACTION';
    const DATA_KEY = 'AISTUDIO_FORGE_DATA';
    const TOOL_STATE_KEYS = {
        googleSearch: 'AISTUDIO_DESIRED_GOOGLE_SEARCH',
        codeExecution: 'AISTUDIO_DESIRED_CODE_EXECUTION',
        urlContext: 'AISTUDIO_DESIRED_URL_CONTEXT'
    };

    // --- 任务轮询 ---
    function pollForJob() {
        // 如果页面正在刷新以应用注入，则不轮询
        if (sessionStorage.getItem(ACTION_KEY)) return;
        GM_xmlhttpRequest({
            method: "GET",
            url: `${LOCAL_SERVER_URL}/get_injection_job`,
            onload: function(response) {
                try {
                    const res = JSON.parse(response.responseText);
                    if (res.status === 'success' && res.job) {
                        console.log("🚚 新任务已获取，准备注入...");
                        sessionStorage.setItem(DATA_KEY, JSON.stringify(res.job));
                        sessionStorage.setItem(ACTION_KEY, 'APPLY_INJECTION');
                        location.reload(); // 刷新页面以触发拦截器
                    }
                } catch (e) { /* 静默处理 */ }
            },
            onerror: function(err) { /* 静默处理连接错误 */ }
        });
    }

    // --- 数据转换器 ---

    // 将标准 JSON Schema 转换为 AI Studio 内部数组格式
    function convertSchemaToInternalFormat(schema) {
        if (!schema || !schema.type) return null;
        const typeMap = { "string": 1, "number": 2, "integer": 3, "boolean": 4, "object": 6, "array": 5 };
        const typeCode = typeMap[schema.type.toLowerCase()];
        if (!typeCode) return null;

        if (typeCode === 6) { // Object
            const internalProperties = [];
            if (schema.properties) {
                for (const key in schema.properties) {
                    const subSchema = schema.properties[key];
                    const internalSubSchema = convertSchemaToInternalFormat(subSchema);
                    if (internalSubSchema) {
                        internalProperties.push([key, internalSubSchema]);
                    }
                }
            }
            return [6, null, null, null, null, null, internalProperties];
        }
        if (typeCode === 5) { // Array
             const itemSchema = schema.items ? convertSchemaToInternalFormat(schema.items) : [1]; // 如果未指定，默认为字符串数组
             return [5, null, null, null, null, itemSchema];
        }
        if (typeCode === 1 && schema.enum && Array.isArray(schema.enum)) { // String with enum
            return [1, null, null, null, schema.enum];
        }
        return [typeCode]; // Simple types
    }

    // 将标准 "tools" 数组转换为 AI Studio 内部函数定义格式
    function convertToolsToInternalFormat(tools) {
        if (!tools || !Array.isArray(tools)) return null;
        const functionDeclarations = [];

        tools.forEach(tool => {
            if (tool.type === 'function' && tool.function) {
                const func = tool.function;
                const parametersSchema = func.parameters ? convertSchemaToInternalFormat(func.parameters) : null;
                // AI Studio 内部格式: [name, description, params_schema, required_array, null, 0]
                functionDeclarations.push([
                    func.name,
                    func.description || "",
                    parametersSchema,
                    func.parameters?.required || [], // 'required' 数组
                    null,
                    0
                ]);
            }
        });

        return functionDeclarations.length > 0 ? functionDeclarations : null;
    }

    // --- 核心数据合并函数 (v7.1) ---
    function mergeData(freshTemplate, jobData) {
        const newPayload = JSON.parse(JSON.stringify(freshTemplate));
        const settingsBlock = newPayload[0][3];

        // 1. 注入基础模型参数
        settingsBlock[0] = jobData.temperature ?? settingsBlock[0];
        settingsBlock[1] = jobData.stop ?? settingsBlock[1];
        if (jobData.model) settingsBlock[2] = `models/${jobData.model}`;
        settingsBlock[4] = jobData.top_p ?? settingsBlock[4];
        settingsBlock[5] = jobData.top_k ?? settingsBlock[5];
        settingsBlock[6] = jobData.max_tokens ?? settingsBlock[6];
        if (jobData.thinking_budget !== undefined) settingsBlock[24] = jobData.thinking_budget;
        // ... (其他参数注入可以按需添加)

        // 2. 注入安全设置
        if (jobData.safety_settings) {
            const categoryMap = {"HARM_CATEGORY_HARASSMENT": 7, "HARM_CATEGORY_HATE_SPEECH": 8, "HARM_CATEGORY_SEXUALLY_EXPLICIT": 9, "HARM_CATEGORY_DANGEROUS_CONTENT": 10};
            const thresholdMap = {"HARM_BLOCK_THRESHOLD_UNSPECIFIED": 5, "BLOCK_NONE": 4, "BLOCK_LOW_AND_ABOVE": 3, "BLOCK_MEDIUM_AND_ABOVE": 2, "BLOCK_ONLY_HIGH": 1};
            jobData.safety_settings.forEach(setting => {
                const categoryNum = categoryMap[setting.category];
                const thresholdNum = thresholdMap[setting.threshold];
                if (categoryNum && thresholdNum !== undefined) {
                    const targetSetting = settingsBlock[7].find(s => s && s[2] === categoryNum);
                    if (targetSetting) targetSetting[3] = thresholdNum;
                }
            });
        }

        // 3. 【【【核心修正】】】处理互斥的输出模式
        if (jobData.response_schema) {
            console.log("✅ 配置【结构化输出】模式。");
            settingsBlock[8] = "application/json"; // 模式: JSON
            settingsBlock[10] = convertSchemaToInternalFormat(jobData.response_schema); // 索引 10: 注入 Schema
            settingsBlock[11] = null; // 索引 11: 清空函数定义
        } else if (jobData.tools && Array.isArray(jobData.tools)) {
            console.log("✅ 配置【函数调用】模式。");
            settingsBlock[8] = "text/plain"; // 模式: Text
            settingsBlock[10] = null; // 索引 10: 清空 Schema 定义
            settingsBlock[11] = convertToolsToInternalFormat(jobData.tools); // 索引 11: 注入函数定义

            // 处理开关型工具 (Google Search, Code Execution, etc.)
            const hasTool = (name) => jobData.tools.some(t => t[name]);
            const googleSearchOn = hasTool('googleSearch');
            const codeExecutionOn = hasTool('codeExecution');
            const urlContextOn = hasTool('urlContext');
            settingsBlock[14] = googleSearchOn ? 1 : 0;
            settingsBlock[9] = codeExecutionOn ? 1 : 0;
            settingsBlock[17] = urlContextOn ? 1 : 0;
            sessionStorage.setItem(TOOL_STATE_KEYS.googleSearch, googleSearchOn);
            sessionStorage.setItem(TOOL_STATE_KEYS.codeExecution, codeExecutionOn);
            sessionStorage.setItem(TOOL_STATE_KEYS.urlContext, urlContextOn);
        } else {
            console.log("✅ 配置【标准文本】模式。");
            settingsBlock[8] = "text/plain";
            settingsBlock[10] = null; // 清空 Schema
            settingsBlock[11] = null; // 清空函数
        }

        // 4. 注入对话历史和系统提示词
        let systemPrompt = "";
        const historyMessages = [];
        (jobData.messages || []).forEach(m => {
            if (m.role === 'system') systemPrompt = m.content;
            else historyMessages.push(m);
        });
        newPayload[0][12] = systemPrompt ? [systemPrompt] : null;

        const flatMessageList = [];
        let currentInputText = "";
        if (historyMessages.length > 0 && historyMessages[historyMessages.length - 1].role === 'user') {
            currentInputText = historyMessages.pop().content;
        }
        for (const message of historyMessages) {
            if (message.role === 'tool') {
                // 【【【新】】】处理工具调用结果
                const toolCallId = message.tool_call_id; // 从OpenAI格式获取ID
                const toolContent = JSON.stringify({ "result": message.content }); // 将内容包装成AI Studio期望的JSON字符串
                 // 构造AI Studio内部的工具结果格式
                flatMessageList.push([
                    null, null, null, null, null, null, null, null, "tool",
                    null, null, null, null, null, null, null, null, null, null, null, null,
                    [
                        [
                            toolCallId, // 对应的函数调用ID
                            [toolContent] // 包含结果的数组
                        ]
                    ]
                ]);
            } else if (message.role === 'assistant') {
                 // 处理模型的回复，可能包含文本和工具调用
                const hasToolCalls = message.tool_calls && message.tool_calls.length > 0;
                const textContent = message.content || (hasToolCalls ? "" : " "); // 如果有工具调用但没文本，给个空字符串

                const modelResponse = [
                    textContent, null, null, null, null, null, null, null, "model",
                    null, null, null, null, null, null, null, 1, null, null, null, null
                ];

                if (hasToolCalls) {
                    const internalToolCalls = message.tool_calls.map(tc => {
                        const args = JSON.parse(tc.function.arguments);
                        const argsArray = Object.entries(args).map(([key, value]) => [key, [null, value]]); // 简化版参数转换
                        return [tc.function.name, [[...argsArray]]];
                    });
                     modelResponse[21] = internalToolCalls; // 注入工具调用
                }
                flatMessageList.push(modelResponse);

            } else { // user
                const roleSpecificData = [null, null, 2];
                flatMessageList.push([message.content, null, null, null, null, null, null, null, "user", null, null, null, null, null, null, null, ...roleSpecificData]);
            }
        }
        const inputBoxState = [[currentInputText, null, null, null, null, null, null, null, "user"]];
        newPayload[0][13] = [flatMessageList, inputBoxState];

        return newPayload;
    }

    // --- 智能等待与 UI 校正器 ---
    function waitForElement(selector, timeout = 5000) {
        return new Promise((resolve, reject) => {
            const intervalTime = 100;
            let elapsedTime = 0;
            const interval = setInterval(() => {
                const element = document.querySelector(selector);
                if (element && element.offsetParent !== null) { // 确保元素可见
                    clearInterval(interval);
                    resolve(element);
                }
                elapsedTime += intervalTime;
                if (elapsedTime >= timeout) {
                    clearInterval(interval);
                    reject(new Error(`Element "${selector}" not found or not visible within ${timeout}ms`));
                }
            }, intervalTime);
        });
    }

    async function verifyAndCorrectUITools() {
        // 仅当 sessionStorage 中有工具状态时才运行
        if (!sessionStorage.getItem(TOOL_STATE_KEYS.googleSearch)) return;

        console.log('🧐 UI 校正器启动...');
        let panelWasOpenedByScript = false;
        try {
            const panelContentSelector = 'ms-prompt-run-settings';
            let panelContent = document.querySelector(panelContentSelector);

            if (!panelContent || panelContent.offsetParent === null) {
                console.log('   - 设置面板已关闭。正在打开...');
                const settingsButton = await waitForElement('button[mattooltip="Show run settings"]');
                settingsButton.click();
                panelWasOpenedByScript = true;
            } else {
                console.log('   - 设置面板已打开。直接检查。');
            }

            // 等待面板内容渲染完成
            await waitForElement(`${panelContentSelector} .settings-item h3`);
            console.log('   - 面板内容已准备就绪。');

            const checkAndClick = async (toolLabel, desiredState) => {
                const allH3s = document.querySelectorAll('.settings-item h3, .tool-setting-label');
                let targetContainer = null;
                allH3s.forEach(h3 => {
                    if (h3.textContent.trim() === toolLabel) {
                        targetContainer = h3.closest('.settings-item, ms-browse-as-a-tool');
                    }
                });
                if (!targetContainer) return;

                const toggleButton = targetContainer.querySelector('button[role="switch"]');
                if (!toggleButton) return;

                const isCurrentlyOn = toggleButton.getAttribute('aria-checked') === 'true';
                if (desiredState !== isCurrentlyOn) {
                    console.log(`   - ❗ 状态不匹配 [${toolLabel}]。需要: ${desiredState}, 当前: ${isCurrentlyOn}。正在点击...`);
                    toggleButton.click();
                } else {
                    console.log(`   - ✅ 状态正确 [${toolLabel}]。`);
                }
            };

            await checkAndClick('Grounding with Google Search', sessionStorage.getItem(TOOL_STATE_KEYS.googleSearch) === 'true');
            await checkAndClick('Code execution', sessionStorage.getItem(TOOL_STATE_KEYS.codeExecution) === 'true');
            await checkAndClick('URL context', sessionStorage.getItem(TOOL_STATE_KEYS.urlContext) === 'true');

        } catch (error) {
            console.error("UI 校正器失败:", error);
        } finally {
            if (panelWasOpenedByScript) {
                const closeButton = document.querySelector('button[aria-label="Close run settings panel"]');
                if (closeButton) {
                    console.log('   - 正在关闭由脚本打开的设置面板...');
                    closeButton.click();
                }
            }
            // 清理状态，防止下次刷新时错误执行
            Object.values(TOOL_STATE_KEYS).forEach(key => sessionStorage.removeItem(key));
            console.log('🧐 UI 校正器完成。');
        }
    }

    // --- 网络拦截器 ---
    const originalXhrOpen = window.XMLHttpRequest.prototype.open;
    const originalDescriptor = Object.getOwnPropertyDescriptor(window.XMLHttpRequest.prototype, 'responseText');

    window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        if (typeof url === 'string' && url.includes(TARGET_URL_PART)) {
            Object.defineProperty(this, 'responseText', {
                get: function() {
                    const action = sessionStorage.getItem(ACTION_KEY);
                    if (this.readyState === 4 && action === 'APPLY_INJECTION') {
                        const freshTemplate = JSON.parse(originalDescriptor.get.call(this));
                        const jobData = JSON.parse(sessionStorage.getItem(DATA_KEY));
                        sessionStorage.removeItem(ACTION_KEY);
                        sessionStorage.removeItem(DATA_KEY);

                        const forgedResponse = JSON.stringify(mergeData(freshTemplate, jobData));

                        // 【【【新信标】】】
                        // 注入完成后，设置一个标志，告诉 Automator 可以开始工作了
                        console.log('✅ History Forger: 注入完成，设置对话就绪信标 (AUTOMATION_READY)。');
                        sessionStorage.setItem('AUTOMATION_READY', 'true');

                        return forgedResponse;
                    }
                    return originalDescriptor.get.apply(this);
                },
                configurable: true
            });
        }
        return originalXhrOpen.apply(this, [method, url, ...rest]);
    };

    // --- 启动脚本 ---
    window.addEventListener('load', () => {
        // 延迟启动，给页面一些初始化的时间
        setTimeout(() => {
            // 开始轮询任务
            setInterval(pollForJob, POLLING_INTERVAL);
            // 执行一次性的 UI 校正
            verifyAndCorrectUITools();
        }, 2500);
    });

})();