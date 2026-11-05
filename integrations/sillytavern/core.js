export function describeTurnFailure(status, code) {
    if (code === 'llm_provider_unavailable' || status === 503) {
        return {
            title: 'Campaign Manager: proveedor no disponible',
            message: 'No se ha podido contactar con el proveedor del modelo. Comprueba que Ollama esté funcionando y vuelve a intentarlo con el mismo mensaje.',
        };
    }
    if (code === 'invalid_llm_response' || status === 502) {
        return {
            title: 'Campaign Manager: respuesta no válida',
            message: 'El modelo no ha devuelto una resolución que se pueda aplicar con seguridad. Puedes reintentar la misma acción; no se han autorizado consecuencias nuevas.',
        };
    }
    if (code === 'turn_resolution_failed' || code === 'internal_error' || (Number.isInteger(status) && status >= 500)) {
        return {
            title: 'Campaign Manager: error interno',
            message: 'No se ha podido resolver el turno por un error interno. La generación se ha detenido para proteger el estado de la campaña. Revisa los logs del backend antes de reintentarlo.',
        };
    }
    if (code === 'conflict' || status === 409) {
        return {
            title: 'Campaign Manager: conflicto de turno',
            message: 'El estado del turno ha cambiado o existe otra operación en curso. Espera a que termine y vuelve a intentarlo; no regeneres repetidamente el mismo turno.',
        };
    }
    if (code === 'validation_error' || code === 'bad_request' || status === 422 || status === 400) {
        return {
            title: 'Campaign Manager: petición no válida',
            message: 'El backend no ha podido validar la acción enviada. Comprueba el mensaje y la configuración de campaña antes de intentarlo de nuevo.',
        };
    }
    if (status === null || status === undefined) {
        return {
            title: 'Campaign Manager: backend inaccesible',
            message: 'No se ha podido conectar con el backend. Comprueba que Campaign Manager esté iniciado y que la URL configurada sea correcta.',
        };
    }
    return {
        title: 'Campaign Manager: no se pudo resolver el turno',
        message: 'La generación se ha detenido porque Campaign Manager no pudo confirmar la resolución. Consulta los logs del backend y vuelve a intentarlo cuando el problema esté resuelto.',
    };
}

export function summarizeConnectionReadiness(payload) {
    if (!payload || typeof payload !== "object") {
        return { ready: false, message: "Invalid backend response." };
    }

    const issues = [];
    const campaign = payload.campaign;
    const session = payload.session;
    const character = payload.active_character;
    const context = payload.context;

    if (!campaign || !Number.isInteger(campaign.id) || !campaign.name) {
        issues.push("campaign is not configured");
    }
    if (!session || !Number.isInteger(session.id) || !session.title) {
        issues.push("no active session");
    }
    if (!character || !Number.isInteger(character.entity_id)) {
        issues.push("no active character");
    }
    if (!context || typeof context.context !== "string" || !context.context.trim()) {
        issues.push("campaign context is empty");
    }

    if (issues.length) {
        return {
            ready: false,
            message: `Backend connected, but setup is incomplete: ${issues.join(", ")}.`,
        };
    }

    const characterLabel = [
        character.class_name || "Character",
        `level ${character.level ?? "?"}`,
    ].join(" ");

    return {
        ready: true,
        message: `Ready: ${campaign.name} · ${session.title} · ${characterLabel}`,
    };
}

export function buildRetrievalQuery(
    configuredQuery,
    playerInput,
) {
    const normalizedConfiguredQuery =
        typeof configuredQuery === "string"
            ? configuredQuery.trim()
            : "";

    const normalizedPlayerInput =
        typeof playerInput === "string"
            ? playerInput.trim()
            : "";

    if (
        !normalizedConfiguredQuery ||
        !normalizedPlayerInput
    ) {
        return "";
    }

    return [
        normalizedConfiguredQuery,
        "",
        "Acción actual del jugador:",
        normalizedPlayerInput,
    ].join("\n");
}

export function buildStableTurnIdentityInput(
    chatId,
    playerMessageIndex,
) {
    if (
        typeof chatId !== 'string' ||
        !chatId.trim()
    ) {
        throw new Error(
            'chatId is required.',
        );
    }

    if (
        !Number.isInteger(playerMessageIndex) ||
        playerMessageIndex < 0
    ) {
        throw new Error(
            'playerMessageIndex must be a non-negative integer.',
        );
    }

    return [
        'campaign-manager-turn-v2',
        chatId.trim(),
        String(playerMessageIndex),
    ].join('|');
}


export function selectClarificationChallenge(
    clarificationState,
    answer,
    answerExternalTurnId = null,
) {
    if (
        !clarificationState ||
        typeof clarificationState !== 'object' ||
        typeof answer !== 'string' ||
        !answer.trim() ||
        clarificationState.has_clarification !== true
    ) {
        return null;
    }

    if (
        (
            (
                typeof answerExternalTurnId === 'string' &&
                clarificationState.last_answer_external_turn_id === answerExternalTurnId
            ) ||
            (
                !answerExternalTurnId &&
                clarificationState.last_answer === answer.trim()
            )
        ) &&
        typeof clarificationState.last_pending_clarification_id === 'string' &&
        clarificationState.last_pending_clarification_id
    ) {
        return {
            pendingClarificationId:
                clarificationState.last_pending_clarification_id,
            retry: true,
        };
    }

    if (
        ['awaiting_input', 'planning'].includes(clarificationState.lifecycle_state) &&
        typeof clarificationState.pending_clarification_id === 'string' &&
        clarificationState.pending_clarification_id
    ) {
        return {
            pendingClarificationId:
                clarificationState.pending_clarification_id,
            retry: false,
        };
    }

    return null;
}


export async function findClarificationOrigin(
    chatMessages,
    playerMessage,
    currentAnswer,
    currentAnswerExternalTurnId,
    createTurnId,
    getClarificationState,
) {
    if (
        !Array.isArray(chatMessages) ||
        typeof createTurnId !== 'function' ||
        typeof getClarificationState !== 'function' ||
        typeof currentAnswer !== 'string' ||
        !currentAnswer.trim()
    ) {
        return null;
    }

    const currentIndex = chatMessages.findIndex(
        (message) => message === playerMessage,
    );
    if (currentIndex < 0) {
        return null;
    }

    let previousAssistant = null;
    for (let index = currentIndex - 1; index >= 0; index -= 1) {
        const message = chatMessages[index];
        if (
            message &&
            message.is_user !== true &&
            typeof message.mes === 'string'
        ) {
            previousAssistant = message;
            break;
        }
    }

    const earliestIndex = Math.max(0, currentIndex - 24);
    for (let index = currentIndex - 1; index >= earliestIndex; index -= 1) {
        const candidate = chatMessages[index];
        if (
            !candidate ||
            candidate.is_user !== true ||
            typeof candidate.mes !== 'string' ||
            !candidate.mes.trim()
        ) {
            continue;
        }

        const candidateInput = candidate.mes.trim();
        const candidateTurnId = await createTurnId(candidate);
        const state = await getClarificationState(candidateTurnId);
        if (!state?.has_clarification) {
            continue;
        }

        const selected = selectClarificationChallenge(
            state,
            currentAnswer,
            currentAnswerExternalTurnId,
        );
        if (selected) {
            if (
                selected.retry &&
                state.lifecycle_state === 'completed' &&
                typeof state.narrative === 'string' &&
                previousAssistant?.mes?.trim() === state.narrative.trim()
            ) {
                return null;
            }

            return {
                externalTurnId: candidateTurnId,
                playerInput: state.player_input || candidateInput,
                pendingClarificationId: selected.pendingClarificationId,
                retry: selected.retry,
                state,
            };
        }

        if (state.lifecycle_state !== 'awaiting_input') {
            return null;
        }
    }

    return null;
}


export class TurnState {
    constructor() {
        this.turnVersions =
            new Map();

        this.turnNarratives =
            new Map();

        this.nextTurnVersions =
            new Map();

        this.lastProcessedTurnVersionKey =
            null;

        this.failedTurnVersionKey = null;
    }

    async getVersion(
        externalTurnId,
        narrativeText,
        getPersistedState,
    ) {
        if (
            typeof externalTurnId !== 'string' ||
            !externalTurnId.trim()
        ) {
            throw new Error(
                'externalTurnId is required.',
            );
        }

        if (
            typeof narrativeText !== 'string' ||
            !narrativeText.trim()
        ) {
            throw new Error(
                'narrativeText is required.',
            );
        }

        if (
            typeof getPersistedState !== 'function'
        ) {
            throw new Error(
                'getPersistedState must be a function.',
            );
        }

        const normalizedExternalTurnId =
            externalTurnId.trim();

        const normalizedNarrative =
            narrativeText.trim();

        /*
         * The backend is authoritative.
         *
         * If this local state does not know the turn yet,
         * restore the currently active backend version before
         * deciding whether this is an existing narrative or
         * a new regeneration.
         */
        if (
            !this.turnVersions.has(
                normalizedExternalTurnId,
            )
        ) {
            const persistedState =
                await getPersistedState(
                    normalizedExternalTurnId,
                );

            if (
                !persistedState ||
                typeof persistedState !== 'object'
            ) {
                throw new Error(
                    'Persisted turn state is invalid.',
                );
            }

            if (
                !Number.isInteger(
                    persistedState.active_version,
                ) ||
                persistedState.active_version < 0
            ) {
                throw new Error(
                    'Persisted active version is invalid.',
                );
            }

            this.turnVersions.set(
                normalizedExternalTurnId,
                persistedState.active_version,
            );

            const persistedNextVersion = persistedState.next_version;
            this.nextTurnVersions.set(
                normalizedExternalTurnId,
                Number.isInteger(persistedNextVersion) &&
                    persistedNextVersion > persistedState.active_version
                    ? persistedNextVersion
                    : persistedState.active_version + 1,
            );

            if (
                persistedState.exists &&
                typeof persistedState.narrative ===
                    'string'
            ) {
                this.turnNarratives.set(
                    normalizedExternalTurnId,
                    persistedState.narrative.trim(),
                );
            } else {
                this.turnNarratives.delete(
                    normalizedExternalTurnId,
                );
            }
        }

        const previousNarrative =
            this.turnNarratives.get(
                normalizedExternalTurnId,
            );

        const previousVersion =
            this.turnVersions.get(
                normalizedExternalTurnId,
            ) ?? 0;

        const turnVersionKey =
            `${normalizedExternalTurnId}:${previousVersion}`;

        /*
        * If this version previously failed, reuse it even when
        * regeneration produced a different narrative.
        *
        * The failed version was never committed as active by the
        * backend, so consuming a new version here would create a gap.
        */
        if (
            this.failedTurnVersionKey ===
            turnVersionKey
        ) {
            this.turnNarratives.set(
                normalizedExternalTurnId,
                normalizedNarrative,
            );

            return previousVersion;
        }

        /*
         * Same narrative:
         * same version.
         *
         * This includes retries after a backend failure.
         */
        if (
            previousNarrative ===
            normalizedNarrative
        ) {
            return previousVersion;
        }

        /*
         * Different narrative:
         * regeneration/swipe.
         */
        const nextVersion =
            this.nextTurnVersions.get(normalizedExternalTurnId) ??
            previousVersion + 1;

        this.turnVersions.set(
            normalizedExternalTurnId,
            nextVersion,
        );

        this.nextTurnVersions.set(
            normalizedExternalTurnId,
            nextVersion + 1,
        );

        this.turnNarratives.set(
            normalizedExternalTurnId,
            normalizedNarrative,
        );

        return nextVersion;
    }

    tryMarkProcessing(
        externalTurnId,
        turnVersion,
    ) {
        const turnVersionKey =
            `${externalTurnId}:${turnVersion}`;

        if (
            this.lastProcessedTurnVersionKey ===
            turnVersionKey
        ) {
            return false;
        }

        this.lastProcessedTurnVersionKey =
            turnVersionKey;

        if (
            this.failedTurnVersionKey ===
            turnVersionKey
        ) {
            this.failedTurnVersionKey = null;
        }

        return true;
    }

    markFailed(
        externalTurnId,
        turnVersion,
    ) {
        const turnVersionKey =
            `${externalTurnId}:${turnVersion}`;

        /*
         * Only unlock the turn if the failed request is
         * still the latest locally processed version.
         */
        if (
            this.lastProcessedTurnVersionKey ===
            turnVersionKey
        ) {
            this.lastProcessedTurnVersionKey = null;
            this.failedTurnVersionKey = turnVersionKey;
        }
    }

    reset() {
        this.lastProcessedTurnVersionKey =
            null;

        this.failedTurnVersionKey = null;

        this.turnVersions.clear();
        this.turnNarratives.clear();
        this.nextTurnVersions.clear();
    }
}

export function parseManualRollResults(answer, expectedCount) {
    if (typeof answer !== 'string' || !Number.isInteger(expectedCount) || expectedCount < 1 || expectedCount > 2) {
        return null;
    }
    const tokens = answer.trim().split(/[,;]/).map((value) => value.trim());
    if (tokens.length !== expectedCount || tokens.some((value) => !/^\d{1,2}$/.test(value))) {
        return null;
    }
    const rolls = tokens.map(Number);
    if (rolls.some((value) => value < 1 || value > 20)) {
        return null;
    }
    return rolls;
}


export async function findManualRollOrigin(
    chatMessages,
    playerMessage,
    currentAnswer,
    createTurnId,
    getManualRollState,
) {
    if (
        !Array.isArray(chatMessages) ||
        typeof createTurnId !== 'function' ||
        typeof getManualRollState !== 'function' ||
        typeof currentAnswer !== 'string' ||
        !currentAnswer.trim()
    ) {
        return null;
    }
    const currentIndex = chatMessages.findIndex((message) => message === playerMessage);
    if (currentIndex < 0) return null;
    const currentAnswerExternalTurnId = await createTurnId(playerMessage);
    const earliestIndex = Math.max(0, currentIndex - 24);
    for (let index = currentIndex - 1; index >= earliestIndex; index -= 1) {
        const candidate = chatMessages[index];
        if (!candidate || candidate.is_user !== true || typeof candidate.mes !== 'string' || !candidate.mes.trim()) {
            continue;
        }
        const externalTurnId = await createTurnId(candidate);
        const state = await getManualRollState(externalTurnId);
        if (!state?.has_manual_roll || typeof state.pending_roll_id !== 'string') {
            continue;
        }
        if (
            state.submitted_external_turn_id &&
            state.submitted_external_turn_id !== currentAnswerExternalTurnId
        ) {
            continue;
        }
        const submittedRolls = parseManualRollResults(currentAnswer, state.pending_roll?.count);
        return {
            externalTurnId,
            playerInput: state.player_input || candidate.mes.trim(),
            pendingRollId: state.pending_roll_id,
            rolls: submittedRolls,
            invalid: !submittedRolls,
            state,
        };
    }
    return null;
}
