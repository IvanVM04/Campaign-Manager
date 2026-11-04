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
        clarificationState.last_answer === answer.trim() &&
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