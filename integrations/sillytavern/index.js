import {
    extension_settings,
    getContext,
} from '../../extensions.js';

import {
    chat,
    eventSource,
    event_types,
    getCurrentChatId,
} from '../../../script.js';

import {
    buildRetrievalQuery,
    buildStableTurnIdentityInput,
    TurnState,
} from "./core.js";


const extensionName = 'campaign-manager';

const defaultSettings = {
    enabled: true,
    backendUrl: 'http://127.0.0.1:8765',
    campaignId: 1,
    contextQuery: 'Quiero conocer el estado actual de la campaña.',
};

let settings = null;

const turnState =
    new TurnState();

const resolvedTurnStates = new Map();

// ============================================================
// CAMPAIGN MANAGER CONTEXT FOR GENERATION
// ============================================================

async function getCampaignManagerGenerationContext(
    playerInput,
    externalTurnId,
) {
    const currentSettings = getSettings();

    if (!currentSettings.enabled) {
        return "";
    }

    const backendUrl = currentSettings.backendUrl
        .trim()
        .replace(/\/+$/, "");

    if (!backendUrl) {
        warn(
            "Backend URL is empty. Context was not requested.",
        );

        return "";
    }

    const normalizedPlayerInput =
        typeof playerInput === "string"
            ? playerInput.trim()
            : "";

    if (!normalizedPlayerInput) {
        warn(
            "Player input is empty. Generation context was not requested.",
        );

        return "";
    }

    const configuredQuery =
        typeof currentSettings.contextQuery === "string"
            ? currentSettings.contextQuery.trim()
            : "";

    if (!configuredQuery) {
        warn(
            "Context query is empty. Generation context was not requested.",
        );

        return "";
    }

    /*
     * The configured context query defines WHAT kind of
     * campaign information should be retrieved.
     *
     * The current player input defines WHICH part of that
     * information is relevant to the current generation.
     *
     * Keeping both makes the setting useful without losing
     * turn-specific retrieval.
     */
    const retrievalQuery = buildRetrievalQuery(
        configuredQuery,
        normalizedPlayerInput,
    );

    try {
        const response = await fetch(
            `${backendUrl}/integration/turn/resolve`,
            {
                method: "POST",

                headers: getCampaignHeaders(true),

                body: JSON.stringify({
                    query: retrievalQuery,
                    player_input: normalizedPlayerInput,
                    external_turn_id: externalTurnId,
                }),
            },
        );

        let responseBody = null;

        try {
            responseBody =
                await response.json();
        } catch {
            responseBody = null;
        }

        if (!response.ok) {
            const detail =
                responseBody?.detail;

            let errorMessage;

            if (typeof detail === "string") {
                errorMessage = detail;
            } else if (
                detail !== undefined
            ) {
                errorMessage =
                    JSON.stringify(detail);
            } else {
                errorMessage =
                    "Unknown backend error";
            }

            throw new Error(
                `HTTP ${response.status}: ${errorMessage}`,
            );
        }

        if (
            !responseBody ||
            typeof responseBody !== "object"
        ) {
            throw new Error(
                "Campaign Manager returned an invalid context response",
            );
        }

        if (
            !responseBody.context ||
            typeof responseBody.context !== "object"
        ) {
            throw new Error(
                "Campaign Manager response does not contain a context object",
            );
        }

        if (
            typeof responseBody.context.context !==
            "string"
        ) {
            throw new Error(
                "Campaign Manager context object does not contain a context string",
            );
        }

        if (
            typeof responseBody.lifecycle_state !== 'string' ||
            typeof responseBody.committed_resolution !== 'string'
        ) {
            throw new Error(
                "Campaign Manager response does not contain durable resolution evidence",
            );
        }

        resolvedTurnStates.set(
            externalTurnId,
            {
                lifecycleState: responseBody.lifecycle_state,
                clarificationQuestion: responseBody.clarification_question ?? null,
            },
        );

        if (responseBody.clarification_question) {
            return [
                responseBody.context.context.trim(),
                '',
                '=== ACLARACIÓN NECESARIA ===',
                'Campaign Manager no ha confirmado consecuencias para esta acción.',
                'Formula la siguiente pregunta al jugador y no describas cambios de estado como si hubieran ocurrido.',
                responseBody.clarification_question,
            ].join('\n');
        }

        if (responseBody.legacy_replay) {
            return [
                responseBody.context.context.trim(),
                '',
                '=== REGENERACIÓN DE TURNO HISTÓRICO ===',
                'Este turno fue procesado por una versión anterior. Conserva el estado existente y no propongas consecuencias nuevas.',
                responseBody.committed_resolution,
            ].join('\n');
        }

        return [
            responseBody.context.context.trim(),
            '',
            '=== RESOLUCIÓN COMPROMETIDA — FUENTE DE VERDAD ===',
            'Las consecuencias y resultados siguientes ya están confirmados por Campaign Manager.',
            'No inventes cambios de estado, no contradigas estos resultados y limita la narración a presentarlos.',
            responseBody.committed_resolution,
        ].join('\n');

    } catch (error) {
        console.warn(
            "[Campaign Manager] Failed to obtain generation context:",
            error,
        );

        return "";
    }
}


// ============================================================
// SILLYTAVERN GENERATION INTERCEPTOR
// ============================================================

globalThis.campaignManagerGenerateInterceptor =
    async function (
        chatMessages,
        contextSize,
        abort,
        type,
    ) {
        const currentSettings =
            getSettings();

        /*
         * SillyTavern uses quiet generations for internal
         * operations such as chat summarization.
         *
         * Campaign Manager world state is generation context
         * for the actual narrative response, not for internal
         * SillyTavern processing.
         *
         * Do not inject Campaign Manager context into quiet
         * generations, and explicitly clear any previous
         * extension prompt so it cannot leak into the quiet
         * generation.
         */
        if (type === 'quiet') {
            await clearCampaignManagerContext();

            log(
                'Skipping Campaign Manager context for quiet generation.',
            );

            return;
        }

        if (!currentSettings.enabled) {
            await clearCampaignManagerContext();
            return;
        }

        if (!Array.isArray(chatMessages)) {
            warn(
                'Generation interceptor received invalid chat.',
            );

            await clearCampaignManagerContext();
            return;
        }

        if (chatMessages.length === 0) {
            await clearCampaignManagerContext();
            return;
        }

        /*
         * Find the most recent user message.
         *
         * Do not assume that the user message is the
         * last element of the array because other
         * extensions may modify the generation context.
         */
        let playerInput = '';

        for (
            let index = chatMessages.length - 1;
            index >= 0;
            index -= 1
        ) {
            const message =
                chatMessages[index];

            if (
                message &&
                message.is_user === true &&
                typeof message.mes === 'string'
            ) {
                playerInput =
                    message.mes.trim();

                break;
            }
        }

        if (!playerInput) {
            warn(
                'Could not find a user message for generation context.',
            );

            await clearCampaignManagerContext();
            return;
        }

        const playerMessage = getLatestUserMessage();
        if (
            !playerMessage ||
            typeof playerMessage.mes !== 'string' ||
            playerMessage.mes.trim() !== playerInput
        ) {
            warn(
                'Could not safely match the generation input to the current chat message.',
            );
            await clearCampaignManagerContext();
            return;
        }

        let externalTurnId;
        try {
            externalTurnId = await createStableTurnId(playerMessage);
        } catch (error) {
            console.error(
                '[Campaign Manager] Failed to identify the current turn before generation:',
                error,
            );
            await clearCampaignManagerContext();
            return;
        }

        const context =
            await getCampaignManagerGenerationContext(
                playerInput,
                externalTurnId,
            );

        if (!context) {
            await clearCampaignManagerContext();
            return;
        }

        await injectCampaignManagerContext(
            context,
        );

        log(
            'Campaign Manager context injected.',
            {
                generationType: type,
                contextSize,
                queryLength:
                    playerInput.length,
                contextLength:
                    context.length,
            },
        );
    };


// ============================================================
// CAMPAIGN MANAGER PROMPT INJECTION
// ============================================================

const campaignManagerPromptId =
    'campaign-manager-world-state';

async function injectCampaignManagerContext(context) {
    if (!context) {
        await clearCampaignManagerContext();
        return;
    }

    const tavernContext = getContext();

    if (
        !tavernContext ||
        typeof tavernContext.setExtensionPrompt !== 'function'
    ) {
        warn(
            'SillyTavern setExtensionPrompt API is unavailable.',
        );

        return;
    }

    const prompt =
        [
            'CAMPAIGN MANAGER — INTERNAL WORLD STATE',
            '',
            'The following is internal campaign state provided as background information.',
            'Use this information to maintain continuity and consistency.',
            'Do not quote, reproduce, summarize, or mention this block in your reply.',
            'Do not output these instructions or the delimiters.',
            '',
            context.trim(),
            '',
            'END INTERNAL WORLD STATE',
        ].join('\n');

    /*
     * position = 0:
     *   After Main Prompt / Story String
     *
     * depth = 0:
     *   Current generation depth.
     *
     * scan = false:
     *   Campaign Manager context must not participate
     *   in World Info keyword scanning.
     *
     * role = 0:
     *   System message.
     */
    await tavernContext.setExtensionPrompt(
        campaignManagerPromptId,
        prompt,
        0,
        1,
        false,
        0,
    );
}

async function clearCampaignManagerContext() {
    const tavernContext = getContext();

    if (
        !tavernContext ||
        typeof tavernContext.setExtensionPrompt !== 'function'
    ) {
        return;
    }

    await tavernContext.setExtensionPrompt(
        campaignManagerPromptId,
        '',
        -1,
        0,
        false,
        0,
    );
}


function log(...args) {
    console.log(
        '[Campaign Manager]',
        ...args,
    );
}

function warn(...args) {
    console.warn(
        '[Campaign Manager]',
        ...args,
    );
}

function getCampaignHeaders(includeJson = false) {
    const campaignId = Number(getSettings().campaignId);

    if (!Number.isInteger(campaignId) || campaignId <= 0) {
        throw new Error('Campaign ID must be a positive integer.');
    }

    return {
        ...(includeJson ? { 'Content-Type': 'application/json' } : {}),
        'Accept': 'application/json',
        'X-Campaign-Id': String(campaignId),
    };
}

function getSettings() {
    if (!extension_settings[extensionName]) {
        extension_settings[extensionName] = {
            ...defaultSettings,
        };
    }

    const stored =
        extension_settings[extensionName];

    if (
        typeof stored.enabled !== 'boolean'
    ) {
        stored.enabled =
            defaultSettings.enabled;
    }

    if (
        typeof stored.backendUrl !== 'string' ||
        !stored.backendUrl.trim()
    ) {
        stored.backendUrl =
            defaultSettings.backendUrl;
    }

    if (!Number.isInteger(Number(stored.campaignId)) || Number(stored.campaignId) <= 0) {
        stored.campaignId = defaultSettings.campaignId;
    } else {
        stored.campaignId = Number(stored.campaignId);
    }

    if (
        typeof stored.contextQuery !== 'string' ||
        !stored.contextQuery.trim()
    ) {
        stored.contextQuery =
            defaultSettings.contextQuery;
    }

    settings = stored;

    return settings;
}

function saveSettings() {
    if (
        typeof saveSettingsDebounced ===
        'function'
    ) {
        saveSettingsDebounced();
    }
}

function createSettingsUi() {
    const existingElement =
        document.getElementById(
            'campaign-manager-extension-settings',
        );

    if (existingElement) {
        return;
    }

    const settingsContainer =
        document.createElement('div');

    settingsContainer.id =
        'campaign-manager-extension-settings';

    settingsContainer.className =
        'campaign-manager-settings';

    settingsContainer.innerHTML = `
        <div class="inline-drawer">
            <div class="inline-drawer-toggle inline-drawer-header">
                <b>Campaign Manager</b>
                <div
                    class="inline-drawer-icon fa-solid fa-circle-chevron-down"
                ></div>
            </div>

            <div class="inline-drawer-content">
                <label class="checkbox_label">
                    <input
                        id="campaign-manager-enabled"
                        type="checkbox"
                    >
                    <span>Enabled</span>
                </label>

                <div class="campaign-manager-setting">
                    <label for="campaign-manager-url">
                        Backend URL
                    </label>

                    <input
                        id="campaign-manager-url"
                        type="text"
                        class="text_pole"
                        placeholder="http://127.0.0.1:8765"
                    >
                </div>

                <div class="campaign-manager-setting">
                    <label for="campaign-manager-campaign-id">
                        Campaign ID
                    </label>

                    <input
                        id="campaign-manager-campaign-id"
                        type="number"
                        min="1"
                        step="1"
                        class="text_pole"
                        placeholder="1"
                    >
                </div>

                <div class="campaign-manager-setting">
                    <label for="campaign-manager-query">
                        Context query
                    </label>

                    <input
                        id="campaign-manager-query"
                        type="text"
                        class="text_pole"
                        placeholder="Quiero conocer el estado actual de la campaña."
                    >
                </div>

                <div class="campaign-manager-actions">
                    <button
                        id="campaign-manager-test"
                        class="menu_button"
                        type="button"
                    >
                        Test connection
                    </button>
                </div>

                <div
                    id="campaign-manager-status"
                    class="campaign-manager-status"
                >
                    Not tested
                </div>
            </div>
        </div>
    `;

    const extensionsContainer =
        document.querySelector(
            '#extensions_settings',
        );

    if (!extensionsContainer) {
        warn(
            'Could not find #extensions_settings.',
        );

        return;
    }

    extensionsContainer.appendChild(
        settingsContainer,
    );

    bindSettingsUi();
}

function bindSettingsUi() {
    const currentSettings =
        getSettings();

    const enabledElement =
        document.getElementById(
            'campaign-manager-enabled',
        );

    const urlElement =
        document.getElementById(
            'campaign-manager-url',
        );

    const queryElement =
        document.getElementById(
            'campaign-manager-query',
        );

    const campaignIdElement = document.getElementById(
        'campaign-manager-campaign-id',
    );

    const testElement =
        document.getElementById(
            'campaign-manager-test',
        );

    if (
        !enabledElement ||
        !urlElement ||
        !queryElement ||
        !campaignIdElement ||
        !testElement
    ) {
        warn(
            'Could not initialize settings UI.',
        );

        return;
    }

    enabledElement.checked =
        Boolean(
            currentSettings.enabled,
        );

    urlElement.value =
        currentSettings.backendUrl;

    queryElement.value =
        currentSettings.contextQuery;

    campaignIdElement.value = String(currentSettings.campaignId);

    enabledElement.addEventListener(
        'change',
        () => {
            currentSettings.enabled =
                enabledElement.checked;

            saveSettings();
        },
    );

    urlElement.addEventListener(
        'change',
        () => {
            currentSettings.backendUrl =
                urlElement.value.trim();

            saveSettings();
        },
    );

    campaignIdElement.addEventListener('change', () => {
        const campaignId = Number(campaignIdElement.value);
        if (!Number.isInteger(campaignId) || campaignId <= 0) {
            campaignIdElement.value = String(currentSettings.campaignId);
            return;
        }
        currentSettings.campaignId = campaignId;
        saveSettings();
    });

    queryElement.addEventListener(
        'change',
        () => {
            currentSettings.contextQuery =
                queryElement.value.trim();

            saveSettings();
        },
    );

    testElement.addEventListener(
        'click',
        testConnection,
    );
}

async function testConnection() {
    const currentSettings =
        getSettings();

    const statusElement =
        document.getElementById(
            'campaign-manager-status',
        );

    if (!statusElement) {
        return;
    }

    if (!currentSettings.enabled) {
        statusElement.textContent =
            'Extension disabled.';

        return;
    }

    const backendUrl =
        currentSettings.backendUrl
            .trim()
            .replace(/\/+$/, '');

    const query =
        currentSettings.contextQuery
            .trim();

    if (!backendUrl) {
        statusElement.textContent =
            'Backend URL is empty.';

        return;
    }

    if (!query) {
        statusElement.textContent =
            'Context query is empty.';

        return;
    }

    statusElement.textContent =
        'Connecting...';

    try {
        const response =
            await fetch(
                `${backendUrl}/integration/context`,
                {
                    method: 'POST',

                    headers: getCampaignHeaders(true),

                    body: JSON.stringify({
                        query: query,
                    }),
                },
            );

        const responseBody =
            await response.json();

        if (!response.ok) {
            const detail =
                responseBody?.detail;

            let errorMessage;

            if (typeof detail === 'string') {
                errorMessage = detail;
            } else if (detail !== undefined) {
                errorMessage =
                    JSON.stringify(detail);
            } else {
                errorMessage =
                    'Unknown backend error';
            }

            throw new Error(
                `HTTP ${response.status}: ${errorMessage}`,
            );
        }

        if (
            !responseBody?.context ||
            typeof responseBody.context !== 'object'
        ) {
            throw new Error(
                'Campaign Manager response does not contain a context object.',
            );
        }

        if (
            typeof responseBody.context.context !== 'string'
        ) {
            throw new Error(
                'Campaign Manager context object does not contain a context string.',
            );
        }

        const campaignName =
            responseBody?.campaign?.name ??
            'Unknown campaign';

        statusElement.textContent =
            `Connected: ${campaignName}`;

        log(
            'Context received:',
            responseBody,
        );
    } catch (error) {
        console.error(
            '[Campaign Manager] Connection failed:',
            error,
        );

        statusElement.textContent =
            `Connection failed: ${error.message}`;
    }
}

function registerTurnDetection() {
    if (
        !eventSource ||
        !event_types
    ) {
        warn(
            'SillyTavern event system is unavailable.',
        );

        return;
    }

    const messageReceivedEvent =
        event_types.MESSAGE_RECEIVED;

    if (!messageReceivedEvent) {
        warn(
            'MESSAGE_RECEIVED event is unavailable.',
        );

        return;
    }

    eventSource.on(
        messageReceivedEvent,
        onMessageReceived,
    );

    log(
        'Turn detection registered:',
        messageReceivedEvent,
    );
}

function registerChatLifecycleDetection() {
    if (
        !eventSource ||
        !event_types
    ) {
        warn(
            'SillyTavern event system is unavailable.',
        );

        return;
    }

    const chatChangedEvent =
        event_types.CHAT_CHANGED;

    if (!chatChangedEvent) {
        warn(
            'CHAT_CHANGED event is unavailable.',
        );

        return;
    }

    eventSource.on(
        chatChangedEvent,
        () => {
            turnState.reset();
            resolvedTurnStates.clear();

            void clearCampaignManagerContext();

            log(
                'Chat changed. Campaign Manager local turn state reset.',
            );
        },
    );

    log(
        'Chat lifecycle detection registered:',
        chatChangedEvent,
    );
}

async function createStableTurnId(
    playerMessage,
) {
    const chatId = getCurrentChatId();

    if (!chatId) {
        throw new Error(
            'Could not determine the current SillyTavern chat id.',
        );
    }

    const playerMessageIndex =
        chat.findIndex(
            (message) =>
                message === playerMessage,
        );

    if (playerMessageIndex < 0) {
        throw new Error(
            'Could not determine the SillyTavern user message index.',
        );
    }

    const input =
        buildStableTurnIdentityInput(
            chatId,
            playerMessageIndex,
        );

    const encoder =
        new TextEncoder();

    const data =
        encoder.encode(input);

    const hashBuffer =
        await crypto.subtle.digest(
            'SHA-256',
            data,
        );

    const hashArray =
        Array.from(
            new Uint8Array(hashBuffer),
        );

    const hashHex =
        hashArray
            .map(
                (byte) =>
                    byte
                        .toString(16)
                        .padStart(2, '0'),
            )
            .join('');

    return hashHex;
}

async function getPersistedTurnState(
    externalTurnId,
) {
    const currentSettings =
        getSettings();

    const backendUrl =
        currentSettings.backendUrl
            .trim()
            .replace(/\/+$/, '');

    if (!backendUrl) {
        throw new Error(
            'Backend URL is empty.',
        );
    }

    if (
        typeof externalTurnId !== 'string' ||
        !externalTurnId.trim()
    ) {
        throw new Error(
            'externalTurnId is required.',
        );
    }

    const encodedTurnId =
        encodeURIComponent(
            externalTurnId,
        );

    const response =
        await fetch(
            `${backendUrl}/integration/turn/${encodedTurnId}`,
            {
                method: 'GET',

                headers: getCampaignHeaders(),
            },
        );

    let responseBody = null;

    try {
        responseBody =
            await response.json();
    } catch {
        responseBody = null;
    }

    if (!response.ok) {
        const detail =
            responseBody?.detail;

        let errorMessage;

        if (typeof detail === 'string') {
            errorMessage = detail;
        } else if (
            detail !== undefined
        ) {
            errorMessage =
                JSON.stringify(detail);
        } else {
            errorMessage =
                'Unknown backend error';
        }

        throw new Error(
            `HTTP ${response.status}: ${errorMessage}`,
        );
    }

    if (
        !responseBody ||
        typeof responseBody !== 'object'
    ) {
        throw new Error(
            'Campaign Manager returned an invalid turn state.',
        );
    }

    if (
        typeof responseBody.exists !==
        'boolean'
    ) {
        throw new Error(
            'Campaign Manager turn state does not contain a valid exists flag.',
        );
    }

    if (
        !Number.isInteger(
            responseBody.active_version,
        ) ||
        responseBody.active_version < 0
    ) {
        throw new Error(
            'Campaign Manager turn state does not contain a valid active version.',
        );
    }

    if (
        responseBody.exists &&
        typeof responseBody.narrative !==
            'string'
    ) {
        throw new Error(
            'Campaign Manager active turn does not contain a narrative.',
        );
    }

    return responseBody;
}


async function getTurnVersion(
    externalTurnId,
    narrativeText,
) {
    const turnVersion =
        await turnState.getVersion(
            externalTurnId,
            narrativeText,
            getPersistedTurnState,
        );

    log(
        'Turn version resolved.',
        {
            external_turn_id:
                externalTurnId,

            turn_version:
                turnVersion,
        },
    );

    return turnVersion;
}

async function sendTurnToBackend(
    externalTurnId,
    playerInput,
    narrativeText,
    turnVersion,
) {
    const currentSettings =
        getSettings();

    const backendUrl =
        currentSettings.backendUrl
            .trim()
            .replace(/\/+$/, '');

    if (!backendUrl) {
        warn(
            'Backend URL is empty. Turn was not sent.',
        );

        return null;
    }

    if (
        typeof externalTurnId !== 'string' ||
        !externalTurnId.trim()
    ) {
        throw new Error(
            'externalTurnId is required.',
        );
    }

    const payload = {
        external_turn_id:
            externalTurnId,

        turn_version:
            turnVersion,

        player_input:
            playerInput,

        narrative:
            narrativeText,
    };

    log(
        'Sending turn to Campaign Manager:',
        payload,
    );

    const response =
        await fetch(
            `${backendUrl}/integration/turn/complete`,
            {
                method: 'POST',

                headers: getCampaignHeaders(true),

                body: JSON.stringify(
                    payload,
                ),
            },
        );

    let responseBody = null;

    try {
        responseBody =
            await response.json();
    } catch {
        responseBody = null;
    }

    if (!response.ok) {
        const detail =
            responseBody?.detail;

        let errorMessage;

        if (typeof detail === 'string') {
            errorMessage = detail;
        } else if (
            detail !== undefined
        ) {
            errorMessage =
                JSON.stringify(detail);
        } else {
            errorMessage =
                'Unknown backend error';
        }

        throw new Error(
            `HTTP ${response.status}: ${errorMessage}`,
        );
    }

    log(
        'Turn processed successfully:',
        responseBody,
    );

    return responseBody;
}

function getLatestUserMessage() {
    if (!Array.isArray(chat)) {
        return null;
    }

    for (let index = chat.length - 1; index >= 0; index -= 1) {
        const message = chat[index];
        if (message && message.is_user === true) {
            return message;
        }
    }

    return null;
}


function getCurrentTurnMessages() {
    if (!Array.isArray(chat)) {
        return null;
    }

    if (chat.length < 2) {
        return null;
    }

    const narrativeIndex =
        chat.length - 1;

    const narrative =
        chat[narrativeIndex];

    if (!narrative) {
        return null;
    }

    if (narrative.is_user) {
        return null;
    }

    const playerMessageIndex =
        chat.length - 2;

    const playerMessage =
        chat[playerMessageIndex];

    if (!playerMessage) {
        return null;
    }

    if (!playerMessage.is_user) {
        return null;
    }

    return {
        playerMessage,
        narrative,
        playerMessageIndex,
        narrativeIndex,
    };
}

async function onMessageReceived() {
    const currentSettings =
        getSettings();

    if (!currentSettings.enabled) {
        return;
    }

    const turn =
        getCurrentTurnMessages();

    if (!turn) {
        warn(
            'Could not determine the current user/assistant turn.',
        );

        return;
    }

    const {
        playerMessage,
        narrative,
    } = turn;

    const playerInput =
        typeof playerMessage.mes === 'string'
            ? playerMessage.mes.trim()
            : '';

    const narrativeText =
        typeof narrative.mes === 'string'
            ? narrative.mes.trim()
            : '';

    if (!playerInput) {
        warn(
            'Player input is empty. Skipping.',
        );

        return;
    }

    if (!narrativeText) {
        warn(
            'Narrative is empty. Skipping.',
        );

        return;
    }

    let externalTurnId;

    try {
        const playerMessageIndex =
            chat.findIndex(
                (message) =>
                    message === playerMessage,
            );

        if (playerMessageIndex < 0) {
            throw new Error(
                'Could not find the received user message in the current SillyTavern chat.',
            );
        }

        externalTurnId =
            await createStableTurnId(
                playerMessage,
            );
    } catch (error) {
        console.error(
            '[Campaign Manager] Failed to create stable turn id:',
            error,
        );

        return;
    }

    const resolutionState = resolvedTurnStates.get(externalTurnId);
    if (resolutionState?.lifecycleState === 'awaiting_input') {
        log(
            'Campaign Manager requested clarification; no consequence transcript is completed yet.',
            { external_turn_id: externalTurnId },
        );
        return;
    }

    /*
     * A turn identity represents the user message.
     *
     * Different AI swipes therefore intentionally
     * share the same external_turn_id.
     */
    let turnVersion;

    try {
        turnVersion =
            await getTurnVersion(
                externalTurnId,
                narrativeText,
            );
    } catch (error) {
        console.error(
            '[Campaign Manager] Failed to determine turn version:',
            error,
        );

        return;
    }

    const shouldProcess =
        turnState.tryMarkProcessing(
            externalTurnId,
            turnVersion,
        );

    if (!shouldProcess) {
        log(
            'Turn version already processed locally. Skipping duplicate.',
            {
                external_turn_id:
                    externalTurnId,

                turn_version:
                    turnVersion,
            },
        );

        return;
    }

    log(
        'Turn detected:',
        {
            external_turn_id:
                externalTurnId,

            player_input:
                playerInput,

            narrative:
                narrativeText,
        },
    );

    /*
     * Do not await the backend request from
     * the MESSAGE_RECEIVED event handler.
     *
     * SillyTavern must be allowed to finish
     * its own message lifecycle.
     */
    void sendTurnToBackend(
        externalTurnId,
        playerInput,
        narrativeText,
        turnVersion,
    ).catch((error) => {
        /*
        * Allow retry if the backend failed.
        */
        turnState.markFailed(
            externalTurnId,
            turnVersion,
        );

        console.error(
            '[Campaign Manager] Failed to process turn:',
            error,
        );
    });
}


function initializeExtension() {
    const currentSettings =
        getSettings();

    log(
        'Extension loaded.',
        currentSettings,
    );

    createSettingsUi();

    registerTurnDetection();

    registerChatLifecycleDetection();
}

initializeExtension();