import assert from "node:assert/strict";
import test from "node:test";

import {
    describeTurnFailure,
    buildRetrievalQuery,
    summarizeConnectionReadiness,
    findClarificationOrigin,
    findManualRollOrigin,
    parseManualRollResults,
    selectClarificationChallenge,
} from "./core.js";


test(
    "buildRetrievalQuery combines configured query and player input",
    () => {
        const result = buildRetrievalQuery(
            "Estado actual de la campaña.",
            "Abro la puerta.",
        );

        assert.equal(
            result,
            [
                "Estado actual de la campaña.",
                "",
                "Acción actual del jugador:",
                "Abro la puerta.",
            ].join("\n"),
        );
    },
);


test(
    "buildRetrievalQuery trims both values",
    () => {
        const result = buildRetrievalQuery(
            "  Estado actual.  ",
            "  Abro la puerta.  ",
        );

        assert.equal(
            result,
            [
                "Estado actual.",
                "",
                "Acción actual del jugador:",
                "Abro la puerta.",
            ].join("\n"),
        );
    },
);


test(
    "buildRetrievalQuery returns empty string without configured query",
    () => {
        assert.equal(
            buildRetrievalQuery(
                "   ",
                "Abro la puerta.",
            ),
            "",
        );
    },
);


test(
    "buildRetrievalQuery returns empty string without player input",
    () => {
        assert.equal(
            buildRetrievalQuery(
                "Estado actual.",
                "   ",
            ),
            "",
        );
    },
);

test(
    'selectClarificationChallenge returns the active challenge for a new answer',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                pending_clarification_id: '42:active-token',
                last_pending_clarification_id: null,
                last_answer: null,
            },
            'La puerta de roble.',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:active-token',
            retry: false,
        });
    },
);


test(
    'selectClarificationChallenge retries the previously accepted answer before using a newer pending challenge',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                pending_clarification_id: '42:next-token',
                last_pending_clarification_id: '42:previous-token',
                last_answer: 'La puerta de roble.',
            },
            'La puerta de roble.',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:previous-token',
            retry: true,
        });
    },
);


test(
    'selectClarificationChallenge rejects unrelated input after clarification completion',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'completed',
                last_pending_clarification_id: '42:previous-token',
                last_answer: 'La puerta de roble.',
            },
            'Ahora busco la salida.',
        );

        assert.equal(result, null);
    },
);


test(
    'findClarificationOrigin finds the pending action behind one clarification exchange',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const question = { is_user: false, mes: '¿Qué puerta?' };
        const answer = { is_user: true, mes: 'La de roble.' };
        const states = new Map([
            ['turn-original', {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                player_input: 'Abro una puerta.',
                pending_clarification_id: '42:second-question',
                last_pending_clarification_id: '42:first-question',
                last_answer: 'La de roble anterior.',
            }],
        ]);

        const result = await findClarificationOrigin(
            [original, question, answer],
            answer,
            'La de hierro.',
            'answer-two-turn',
            async (message) => message === original ? 'turn-original' : 'answer-turn',
            async (turnId) => states.get(turnId) ?? { has_clarification: false },
        );

        assert.equal(result.externalTurnId, 'turn-original');
        assert.equal(result.playerInput, 'Abro una puerta.');
        assert.equal(result.pendingClarificationId, '42:second-question');
        assert.equal(result.retry, false);
    },
);


test(
    'findClarificationOrigin replays the previous challenge when an accepted answer is retried',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const firstQuestion = { is_user: false, mes: '¿Qué puerta?' };
        const firstAnswer = { is_user: true, mes: 'La de roble.' };
        const secondQuestion = { is_user: false, mes: '¿Con cuidado?' };
        const retryAnswer = { is_user: true, mes: 'La de roble.' };
        const state = {
            has_clarification: true,
            lifecycle_state: 'awaiting_input',
            player_input: 'Abro una puerta.',
            pending_clarification_id: '42:second-question',
            last_pending_clarification_id: '42:first-question',
            last_answer: 'La de roble.',
            last_answer_external_turn_id: 'retry-answer-turn',
        };

        const result = await findClarificationOrigin(
            [original, firstQuestion, firstAnswer, secondQuestion, retryAnswer],
            retryAnswer,
            'La de roble.',
            'retry-answer-turn',
            async (message) => message === original ? 'turn-original' : 'unrelated-turn',
            async (turnId) => turnId === 'turn-original'
                ? state
                : { has_clarification: false },
        );

        assert.equal(result.pendingClarificationId, '42:first-question');
        assert.equal(result.retry, true);
    },
);


test(
    'findClarificationOrigin does not mistake a new turn for a repeated clarification answer',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const question = { is_user: false, mes: '¿Qué puerta?' };
        const answer = { is_user: true, mes: 'La de roble.' };
        const narrative = { is_user: false, mes: 'La puerta de roble se abre.' };
        const newAction = { is_user: true, mes: 'La de roble.' };
        const state = {
            has_clarification: true,
            lifecycle_state: 'completed',
            player_input: 'Abro una puerta.',
            last_pending_clarification_id: '42:first-question',
            last_answer: 'La de roble.',
            last_answer_external_turn_id: 'new-action-turn',
            narrative: 'La puerta de roble se abre.',
        };

        const result = await findClarificationOrigin(
            [original, question, answer, narrative, newAction],
            newAction,
            'La de roble.',
            'new-action-turn',
            async (message) => message === original ? 'turn-original' : 'unrelated-turn',
            async (turnId) => turnId === 'turn-original'
                ? state
                : { has_clarification: false },
        );

        assert.equal(result, null);
    },
);


test(
    'selectClarificationChallenge permits retry recovery while a planning lease is present',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'planning',
                pending_clarification_id: '42:active-token',
                last_pending_clarification_id: null,
                last_answer: null,
            },
            'La puerta de roble.',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:active-token',
            retry: false,
        });
    },
);


test(
    'findClarificationOrigin follows several rounds back to the original action',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const questionOne = { is_user: false, mes: '¿Qué puerta?' };
        const answerOne = { is_user: true, mes: 'La de roble.' };
        const questionTwo = { is_user: false, mes: '¿La abres con cuidado?' };
        const answerTwo = { is_user: true, mes: 'Con cuidado.' };
        const state = {
            has_clarification: true,
            lifecycle_state: 'awaiting_input',
            player_input: 'Abro una puerta.',
            pending_clarification_id: '42:third-question',
            last_pending_clarification_id: '42:second-question',
            last_answer: 'La de roble.',
            last_answer_external_turn_id: 'answer-one-turn',
        };

        const result = await findClarificationOrigin(
            [original, questionOne, answerOne, questionTwo, answerTwo],
            answerTwo,
            'Con cuidado.',
            'answer-two-turn',
            async (message) => message === original ? 'turn-original' : 'answer-turn',
            async (turnId) => turnId === 'turn-original'
                ? state
                : { has_clarification: false },
        );

        assert.equal(result.externalTurnId, 'turn-original');
        assert.equal(result.pendingClarificationId, '42:third-question');
        assert.equal(result.retry, false);
    },
);


test(
    'selectClarificationChallenge uses the active challenge when identical text comes from a new message',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                pending_clarification_id: '42:active-token',
                last_pending_clarification_id: '42:previous-token',
                last_answer: 'Sí.',
                last_answer_external_turn_id: 'message-previous',
            },
            'Sí.',
            'message-current',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:active-token',
            retry: false,
        });
    },
);


test("parseManualRollResults validates exactly the requested d20 results", () => {
    assert.deepEqual(parseManualRollResults("17", 1), [17]);
    assert.deepEqual(parseManualRollResults("4, 19", 2), [4, 19]);
    assert.deepEqual(parseManualRollResults("4;19", 2), [4, 19]);
    assert.equal(parseManualRollResults("0", 1), null);
    assert.equal(parseManualRollResults("21", 1), null);
    assert.equal(parseManualRollResults("4, 19", 1), null);
    assert.equal(parseManualRollResults("4", 2), null);
    assert.equal(parseManualRollResults("I rolled 17", 1), null);
});


test("findManualRollOrigin recovers the original action and rejects malformed dice input", async () => {
    const action = { is_user: true, mes: "Me escondo del guardia." };
    const assistant = { is_user: false, mes: "Lanza dos d20 y dime los resultados." };
    const answer = { is_user: true, mes: "8, 16" };
    const chat = [action, assistant, answer];
    const createTurnId = async (message) => message === action ? "original-turn" : "answer-turn";
    const getState = async (turnId) => turnId === "original-turn" ? {
        has_manual_roll: true,
        pending_roll_id: "42:challenge",
        player_input: action.mes,
        pending_roll: { count: 2, modifier: 5 },
    } : { has_manual_roll: false };

    const origin = await findManualRollOrigin(chat, answer, answer.mes, createTurnId, getState);
    assert.equal(origin.externalTurnId, "original-turn");
    assert.equal(origin.pendingRollId, "42:challenge");
    assert.deepEqual(origin.rolls, [8, 16]);
    assert.equal(origin.invalid, false);

    const invalid = await findManualRollOrigin(chat, answer, "8", createTurnId, getState);
    assert.equal(invalid.invalid, true);
    assert.equal(invalid.pendingRollId, "42:challenge");
});


test("findManualRollOrigin does not associate arbitrary replies without a pending challenge", async () => {
    const action = { is_user: true, mes: "Abro la puerta." };
    const answer = { is_user: true, mes: "12" };
    const chat = [action, answer];
    const origin = await findManualRollOrigin(
        chat,
        answer,
        answer.mes,
        async () => "turn-id",
        async () => ({ has_manual_roll: false }),
    );
    assert.equal(origin, null);
});


test("findManualRollOrigin recovers a completed manual roll only for the original dice reply", async () => {
    const action = { is_user: true, mes: "Me escondo." };
    const answer = { is_user: true, mes: "14" };
    const chat = [action, { is_user: false, mes: "Lanza un d20." }, answer];
    const getState = async () => ({
        has_manual_roll: true,
        lifecycle_state: "completed",
        pending_roll_id: "42:challenge",
        submitted_external_turn_id: "answer-turn",
        player_input: action.mes,
        pending_roll: { count: 1, modifier: 3 },
    });
    const createTurnId = async (message) => message === answer ? "answer-turn" : "action-turn";

    const retry = await findManualRollOrigin(chat, answer, answer.mes, createTurnId, getState);
    assert.equal(retry.externalTurnId, "action-turn");
    assert.deepEqual(retry.rolls, [14]);

    const unrelatedReply = await findManualRollOrigin(
        chat,
        answer,
        answer.mes,
        async (message) => message === answer ? "different-answer-turn" : "action-turn",
        getState,
    );
    assert.equal(unrelatedReply, null);
});


test("summarizeConnectionReadiness confirms a complete playable setup", () => {
    const result = summarizeConnectionReadiness({
        campaign: { id: 7, name: "Puenteviejo" },
        session: { id: 3, title: "Las campanas" },
        active_character: { entity_id: 12, class_name: "Fighter", level: 1 },
        context: { context: "Mara espera junto a la barra." },
    });

    assert.deepEqual(result, {
        ready: true,
        message: "Ready: Puenteviejo · Las campanas · Fighter level 1",
    });
});

test("summarizeConnectionReadiness reports missing playable setup components", () => {
    const result = summarizeConnectionReadiness({
        campaign: { id: 7, name: "Puenteviejo" },
        session: null,
        active_character: null,
        context: { context: " " },
    });

    assert.equal(result.ready, false);
    assert.match(result.message, /no active session/);
    assert.match(result.message, /no active character/);
    assert.match(result.message, /campaign context is empty/);
});

test("summarizeConnectionReadiness rejects a malformed response", () => {
    assert.deepEqual(summarizeConnectionReadiness(null), {
        ready: false,
        message: "Invalid backend response.",
    });
});


test("describeTurnFailure gives actionable guidance for stable backend error codes", () => {
    assert.deepEqual(describeTurnFailure(503, "llm_provider_unavailable"), {
        title: "Campaign Manager: proveedor no disponible",
        message: "No se ha podido contactar con el proveedor del modelo. Comprueba que Ollama esté funcionando y vuelve a intentarlo con el mismo mensaje.",
    });
    assert.match(describeTurnFailure(502, "invalid_llm_response").message, /misma acción/);
    assert.match(describeTurnFailure(500, "turn_resolution_failed").message, /logs del backend/);
    assert.match(describeTurnFailure(409, "conflict").message, /no regeneres repetidamente/);
    assert.match(describeTurnFailure(null, null).message, /backend esté iniciado/);
});
